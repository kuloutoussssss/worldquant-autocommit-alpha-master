# -*- coding: utf-8 -*-
"""
Alpha 策略生成模块

支持两种模式：
1. 随机生成：每次生成不同的因子组合（默认）
2. 固定模板：从配置文件读取固定策略

使用 random_mode=True 启用随机生成模式
"""
import json
import random
import re
from pathlib import Path
from typing import List, Dict, Any, Set, Optional


class AlphaStrategy:
    # 已知的失败模式特征
    FAILURE_PATTERNS = {
        'complex_nesting': {
            'description': '过度嵌套的表达式',
            'indicators': ['power(power(', 'ts_rank(ts_rank(', 'ts_std_dev(ts_std_dev('],
            'weight': 0.8  # 降低使用概率
        },
        'extreme_exponents': {
            'description': '使用极端指数值',
            'indicators': ['power(', 'power('],
            'params': {'power_max': 3},
            'weight': 0.7
        },
        'single_field_excessive': {
            'description': '单一字段过度使用',
            'max_same_field': 3,
            'weight': 0.6
        }
    }

    def __init__(self, seed=None, random_mode=True):
        """
        初始化策略生成器

        Args:
            seed: 随机种子，用于复现结果（默认None表示不设置）
            random_mode: 是否使用随机模式（默认True）
        """
        self.template_file = Path(__file__).parent.parent / "data" / "templates" / "strategy_templates.json"
        self._templates_cache = None
        self.random_mode = random_mode
        self._failed_patterns: Set[str] = set()  # 记录失败过的字段组合
        self._avoid_templates: Set[str] = set()   # 需要避免的模板

        if seed is not None:
            random.seed(seed)
    """Alpha 策略生成器"""

    # 基础字段池（所有数据集共用的基础字段）
    BASE_FIELDS = ['close', 'open', 'high', 'low', 'volume', 'returns', 'cap', 'sharesout', 'vwap', 'adv20']

    def __init__(self, seed=None, random_mode=True):
        """
        初始化策略生成器

        Args:
            seed: 随机种子，用于复现结果（默认None表示不设置）
            random_mode: 是否使用随机模式（默认True）
        """
        self.template_file = Path(__file__).parent.parent / "data" / "templates" / "strategy_templates.json"
        self._templates_cache = None
        self.random_mode = random_mode

        if seed is not None:
            random.seed(seed)

    def _load_templates(self):
        """加载策略模板配置文件"""
        if self._templates_cache is None:
            with open(self.template_file, 'r', encoding='utf-8') as f:
                self._templates_cache = json.load(f)
        return self._templates_cache

    def _rand_choice(self, options, prob=None, k=1):
        """随机选择，支持加权概率
        
        Args:
            options: 选项列表
            prob: 权重列表（可选）
            k: 采样数量（默认1）
        """
        if k == 1:
            return random.choices(options, weights=prob, k=1)[0] if prob else random.choice(options)
        else:
            return random.choices(options, weights=prob, k=k)

    def load_failure_patterns(self, db_path: str = "data/alphas.db", min_fail_count: int = 2) -> int:
        """从数据库加载失败模式，用于避免生成类似的表达式
        
        Args:
            db_path: 数据库路径
            min_fail_count: 最少失败次数（用于纳入失败模式）
        
        Returns:
            加载的失败模式数量
        """
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from core.db_manager import get_database
            
            db = get_database(db_path)
            failed_exprs = db.get_failed_expressions(min_fail_count=min_fail_count, limit=500)
            
            if not failed_exprs:
                print(f"[AlphaStrategy] 未发现失败表达式（失败次数>={min_fail_count}）")
                return 0
            
            # 分析失败模式
            for item in failed_exprs:
                expr = item['expression']
                reason = item.get('fail_reason', '') or ''
                
                # 提取表达式中的字段
                fields_in_expr = self._extract_fields_from_expression(expr)
                
                # 提取使用的函数模板
                funcs = self._extract_functions_from_expression(expr)
                
                # 记录频繁失败的字段组合
                if len(fields_in_expr) >= 1:
                    for field in fields_in_expr:
                        # 记录失败过的字段
                        if f"field:{field}" not in self._failed_patterns:
                            self._failed_patterns.add(f"field:{field}")
                
                # 记录失败原因关键词
                reason_keywords = self._analyze_failure_reason(reason)
                for kw in reason_keywords:
                    self._failed_patterns.add(f"reason:{kw}")
                
                # 记录复杂模板组合
                if len(funcs) > 3:
                    template_key = "|".join(sorted(funcs[:3]))  # 前3个函数组合
                    self._failed_patterns.add(f"template:{template_key}")
            
            print(f"[AlphaStrategy] 已加载 {len(failed_exprs)} 个失败表达式，学习了 {len(self._failed_patterns)} 个失败模式")
            return len(self._failed_patterns)
            
        except Exception as e:
            print(f"[AlphaStrategy] 加载失败模式失败: {e}")
            return 0

    def _extract_fields_from_expression(self, expr: str) -> List[str]:
        """从表达式中提取字段名"""
        # 常见的字段名模式
        field_pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b'
        all_matches = re.findall(field_pattern, expr)
        
        # 过滤掉函数名和关键字
        keywords = {
            'if_else', 'rank', 'delay', 'ts_mean', 'ts_std_dev', 'ts_sum', 'ts_rank',
            'ts_corr', 'ts_zscore', 'ts_decay_linear', 'group_rank', 'group_zscore',
            'group_neutralize', 'group_mean', 'regression_neut', 'power', 'abs',
            'sign', 'log', 'exp', 'sqrt', 'max', 'min', 'clip', 'bucket', 'trade_when',
            'correlation', 'covariance', 'mean', 'std', 'sum', 'product', 'delta',
            'sector', 'industry', 'subindustry', 'cap', 'volume', 'close', 'open',
            'high', 'low', 'returns', 'vwap', 'sharesout', 'adv20'
        }
        
        return [m for m in all_matches if m not in keywords and not m.isdigit()]

    def _extract_functions_from_expression(self, expr: str) -> List[str]:
        """从表达式中提取函数名"""
        func_pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
        return re.findall(func_pattern, expr)

    def _analyze_failure_reason(self, reason: str) -> List[str]:
        """分析失败原因，提取关键词"""
        reason_lower = reason.lower()
        keywords = []
        
        # 常见失败原因关键词
        if 'timeout' in reason_lower:
            keywords.append('timeout')
        if 'complex' in reason_lower or 'nesting' in reason_lower:
            keywords.append('complex')
        if 'memory' in reason_lower or 'resource' in reason_lower:
            keywords.append('resource')
        if 'invalid' in reason_lower or 'syntax' in reason_lower:
            keywords.append('invalid')
        if 'empty' in reason_lower or 'no data' in reason_lower:
            keywords.append('no_data')
        if 'overflow' in reason_lower or 'overflow' in reason_lower:
            keywords.append('overflow')
        if 'concentration' in reason_lower:
            keywords.append('concentration')
        
        return keywords

    def _is_template_safe(self, field: str, template_str: str) -> bool:
        """检查模板是否安全（避免失败过的模式）
        
        Args:
            field: 字段名
            template_str: 模板字符串
        
        Returns:
            True表示安全，False表示应避免
        """
        # 检查是否包含已知失败字段
        if f"field:{field}" in self._failed_patterns:
            # 有失败记录但不是绝对禁止，降低权重即可
            pass
        
        # 检查模板复杂度
        funcs = self._extract_functions_from_expression(template_str)
        if len(funcs) > 3:
            template_key = "|".join(sorted(funcs[:3]))
            if f"template:{template_key}" in self._failed_patterns:
                return False
        
        # 检查失败原因相关的模式
        for pattern in self._failed_patterns:
            if pattern.startswith('reason:'):
                reason_kw = pattern.split(':')[1]
                if reason_kw == 'complex' and len(funcs) > 4:
                    return False
                if reason_kw == 'resource' and len(funcs) > 5:
                    return False
        
        return True

    def _adjust_template_probability(self, base_prob: float, field: str, template_str: str) -> float:
        """根据失败模式调整模板概率
        
        Args:
            base_prob: 基础概率
            field: 字段名
            template_str: 模板字符串
        
        Returns:
            调整后的概率
        """
        prob = base_prob
        
        # 如果字段有失败记录，降低概率
        if f"field:{field}" in self._failed_patterns:
            prob *= 0.7
        
        # 检查模板复杂度
        funcs = self._extract_functions_from_expression(template_str)
        complexity = len(funcs)
        
        if complexity > 4:
            prob *= 0.5
        elif complexity > 3:
            prob *= 0.7
        
        # 检查模板组合是否失败过
        if complexity >= 3:
            template_key = "|".join(sorted(funcs[:3]))
            if f"template:{template_key}" in self._failed_patterns:
                prob *= 0.3  # 大幅降低失败过的模板组合
        
        return prob

    def _maybe_add_smoothing(self, strategy, prob=0.3):
        """随机决定是否添加平滑处理"""
        if not self.random_mode or random.random() > prob:
            return strategy

        smooth_type = self._rand_choice(['ts_decay_linear', 'ts_zscore', 'rank'])
        window = self._rand_choice([5, 10, 15, 20, 30])

        if smooth_type == 'ts_decay_linear':
            return f"ts_decay_linear({strategy}, {window})"
        elif smooth_type == 'ts_zscore':
            return f"ts_zscore({strategy}, {window})"
        else:
            return f"rank({strategy})"

    def _maybe_add_neutralization(self, strategy, prob=0.4):
        """随机决定是否添加中性化"""
        if not self.random_mode or random.random() > prob:
            return strategy

        neut_type = self._rand_choice(['group_rank', 'group_neutralize', 'group_zscore'])
        group = self._rand_choice(['sector', 'subindustry', 'industry'])

        if neut_type == 'group_rank':
            return f"group_rank({strategy}, {group})"
        elif neut_type == 'group_neutralize':
            return f"group_neutralize({strategy}, {group})"
        else:
            return f"group_zscore({strategy}, {group})"

    def _classify_fields(self, datafields: List[str]) -> Dict[str, List[str]]:
        """根据字段名称分类字段
        
        Returns:
            包含分类字段的字典：
            - returns: 收益率类
            - volume: 成交量类
            - cap: 市值类
            - financial: 财务类（包含特定关键词）
            - price: 价格类
            - ratio: 比率类
            - growth: 增长类
            - estimate: 预期类
            - rating: 评级类
            - all: 所有字段
        """
        classified = {
            'returns': [], 'volume': [], 'cap': [], 'financial': [],
            'price': [], 'ratio': [], 'growth': [], 'estimate': [],
            'rating': [], 'all': []
        }
        
        for field in datafields:
            field_lower = field.lower()
            classified['all'].append(field)
            
            if 'return' in field_lower:
                classified['returns'].append(field)
            if 'volume' in field_lower or 'turnover' in field_lower or 'amount' in field_lower:
                classified['volume'].append(field)
            if 'cap' in field_lower or 'market' in field_lower or 'size' in field_lower:
                classified['cap'].append(field)
            if any(k in field_lower for k in ['price', 'close', 'open', 'high', 'low']):
                classified['price'].append(field)
            if any(k in field_lower for k in ['ratio', 'margin', 'rate', 'yield', 'turn']):
                classified['ratio'].append(field)
            if any(k in field_lower for k in ['growth', 'change', 'chg', 'delta', 'increase']):
                classified['growth'].append(field)
            if any(k in field_lower for k in ['estimate', 'forecast', 'target', 'expected']):
                classified['estimate'].append(field)
            if any(k in field_lower for k in ['rating', 'recommend', 'buy', 'sell', 'hold', 'outperform']):
                classified['rating'].append(field)
            # 财务类：包含关键词的字段
            if any(k in field_lower for k in ['sales', 'revenue', 'income', 'profit', 'ebitda', 
                                               'debt', 'asset', 'equity', 'book', 'earning', 'dividend',
                                               'cash', 'flow', 'cost', 'expense', 'margin', 'roa', 'roe', 'roc']):
                classified['financial'].append(field)
        
        # 确保基础字段存在
        for base in self.BASE_FIELDS:
            if base in datafields and base not in classified['all']:
                classified['all'].append(base)
                if 'return' in base:
                    classified['returns'].append(base)
                if 'volume' in base or 'turnover' in base:
                    classified['volume'].append(base)
                if 'cap' in base:
                    classified['cap'].append(base)
                if any(k in base for k in ['price', 'close', 'open', 'high', 'low']):
                    classified['price'].append(base)
        
        # 去重
        for key in classified:
            classified[key] = list(dict.fromkeys(classified[key]))
        
        return classified

    def _build_template_pool(self, field_pool: List[str], corr_fields: List[str]) -> List[tuple]:
        """构建模板池，包含(field, template_func, param_type)
        
        Args:
            field_pool: 主字段池
            corr_fields: 用于相关性计算的字段池
        
        Returns:
            模板列表，每项为 (模板函数, 参数类型, 是否需要主字段)
        """
        templates = []
        groups = ['sector', 'subindustry', 'industry']
        
        # 确保有相关性字段可用
        if not corr_fields:
            corr_fields = ['volume/sharesout', 'returns', 'cap']
        
        for field in field_pool:
            f = field  # 主字段引用
            
            # 1. 日内收益类 (使用主字段)
            templates.append((f"(close - delay({f}, {{d}}))/delay(close, {{d}})", 'delay', True))
            templates.append((f"({f} - delay({f}, {{d}}))/delay({f}, {{d}})", 'delay', True))
            
            # 2. 时间序列类 (使用主字段)
            for w in [5, 10, 15, 20, 30]:
                templates.append((f"ts_std_dev({f}, {w})", 'window', True))
                templates.append((f"ts_rank({f}, {w})", 'window', True))
                templates.append((f"ts_mean({f}, {w})", 'window', True))
                templates.append((f"rank({f} / ts_mean({f}, {w}))", 'window', True))
                templates.append((f"({f} - ts_mean({f}, {w})) / ts_std_dev({f}, {w})", 'window', True))
                templates.append((f"ts_zscore({f}, {w})", 'window', True))
            
            # 3. 相关性类 (使用主字段 × 相关字段)
            for corr_f in corr_fields[:5]:  # 限制相关性字段数量
                for w in [5, 10, 20]:
                    templates.append((f"ts_corr({f}, {corr_f}, {w})", 'window', True))
            
            # 4. 行业中性类
            for g in groups:
                templates.append((f"group_rank({f}, {g})", 'group', True))
                templates.append((f"group_zscore({f}, {g})", 'group', True))
                templates.append((f"group_neutralize({f}, {g})", 'group', True))
            
            # 5. 排名类
            templates.append((f"rank({f})", 'none', True))
            templates.append((f"rank(-1 * {f})", 'none', True))
            templates.append((f"power(rank({f}), 2)", 'none', True))
            templates.append((f"power(rank({f}), 0.5)", 'none', True))
            templates.append((f"if_else(rank({f}) > 0.5, 1, -1)", 'none', True))
            
            # 6. 延迟类
            for d in [1, 2, 3, 5, 10]:
                templates.append((f"{f} - delay({f}, {d})", 'delay', True))
                templates.append((f"delay({f}, {d}) / {f}", 'delay', True))
            
            # 7. 市值中性类
            templates.append((f"rank(-cap) * {f}", 'none', True))
            templates.append((f"rank(-1/cap) * {f}", 'none', True))
            templates.append((f"{f} / cap", 'none', True))
        
        return templates

    def _build_cross_dataset_templates(self, fields1: List[str], fields2: List[str]) -> List[str]:
        """构建跨数据集组合模板
        
        Args:
            fields1: 数据集1字段
            fields2: 数据集2字段
        
        Returns:
            跨数据集表达式列表
        """
        strategies = []
        
        # 采样限制，避免组合爆炸
        sample1 = fields1[:100] if len(fields1) > 100 else fields1
        sample2 = fields2[:50] if len(fields2) > 50 else fields2
        
        # 1. 回归中性化组合
        for f1 in sample1[:30]:  # 限制数量
            for f2 in sample2[:20]:
                strategies.append(f"regression_neut({f1}, {f2})")
                strategies.append(f"regression_neut(rank({f1}), rank({f2}))")
        
        # 2. 条件组合
        for f1 in sample1[:20]:
            for f2 in sample2[:15]:
                strategies.append(f"if_else(rank({f1}) > 0.5, {f2}, -1 * {f2})")
                strategies.append(f"{f1} * {f2}")
                strategies.append(f"rank({f1}) + rank({f2})")
        
        # 3. 分组中性化
        for f1 in sample1[:15]:
            for f2 in sample2[:10]:
                strategies.append(f"group_neutralize({f1} * {f2}, industry)")
                strategies.append(f"group_rank({f1} - {f2}, subindustry)")
        
        # 4. 相关性组合
        for f1 in sample1[:20]:
            for f2 in sample2[:15]:
                for w in [10, 20]:
                    strategies.append(f"ts_corr({f1}, {f2}, {w})")
        
        return strategies

    def get_simulation_data(self, datafields, mode=1, count=100, multi_dataset_fields: Dict[str, List[str]] = None):
        """
        根据模式生成策略列表

        Args:
            datafields: 数据字段列表（主数据集）
            mode: 策略模式
                1 - 基础策略（单因子，充分利用所有字段）
                2 - 多因子组合策略
                3 - 跨数据集组合策略
            count: 生成策略数量（仅在随机模式下生效）
            multi_dataset_fields: 其他数据集的字段字典，格式：{'analyst4': [...], 'pv1': [...]}

        Returns:
            策略表达式列表
        """
        templates = self._load_templates()

        if mode == 1:
            return self.generate_basic_strategy(datafields, templates, count)
        elif mode == 2:
            return self.generate_multi_factor_strategy(datafields, templates, count)
        elif mode == 3:
            # 跨数据集模式
            other_fields = []
            if multi_dataset_fields:
                for ds_name, fields in multi_dataset_fields.items():
                    other_fields.extend(fields)
            return self.generate_cross_dataset_strategy(datafields, other_fields, count)
        else:
            print("❌ 无效的策略模式")
            return []

    def generate_basic_strategy(self, datafields: List[str], templates: dict, count: int = 100) -> List[str]:
        """生成基础策略（充分利用所有字段）

        随机模式：每次随机组合参数生成不同因子
        固定模式：从模板生成所有因子组合
        
        会自动分析历史失败模式，避免生成类似的高失败率表达式
        """
        strategies = []
        
        # 分类字段
        classified = self._classify_fields(datafields)
        all_fields = classified['all']
        
        if not all_fields:
            return strategies
        
        # 获取相关性字段池（使用分类结果）
        corr_fields = list(set(
            classified['returns'] + classified['volume'] + classified['cap'] + ['volume/sharesout', 'returns', 'cap']
        ))[:20]  # 限制数量
        
        # 构建模板池
        template_pool = self._build_template_pool(all_fields, corr_fields)
        
        # 参数池
        windows = [5, 10, 15, 20, 30, 60]
        delays = [1, 2, 3, 5, 10]
        groups = ['sector', 'subindustry', 'industry']

        if self.random_mode:
            # 随机模式：随机选择模板组合（带失败模式权重）
            failed_patterns_count = len(self._failed_patterns)
            if failed_patterns_count > 0:
                print(f"[AlphaStrategy] 使用 {failed_patterns_count} 个失败模式调整生成概率")
            
            attempts = 0
            max_attempts = count * 10  # 最多尝试次数，避免无限循环
            
            while len(strategies) < count and attempts < max_attempts:
                attempts += 1
                
                # 计算加权概率选择模板
                template_info = self._rand_choice(template_pool)
                template_str, param_type, needs_field = template_info
                
                # 提取字段（从模板中获取）
                field_in_template = None
                for f in all_fields:
                    if f in template_str:
                        field_in_template = f
                        break
                
                # 根据失败模式调整选择概率
                if field_in_template:
                    prob_adjust = self._adjust_template_probability(1.0, field_in_template, template_str)
                    
                    # 如果概率过低，跳过这个模板
                    if prob_adjust < 0.1 and failed_patterns_count > 10:
                        continue
                    
                    # 随机决定是否使用调整后的概率
                    if random.random() > prob_adjust:
                        continue
                
                # 替换参数
                try:
                    if param_type == 'window':
                        param = self._rand_choice(windows)
                        expr = template_str.format(w=param)
                    elif param_type == 'delay':
                        param = self._rand_choice(delays)
                        expr = template_str.format(d=param)
                    elif param_type == 'group':
                        param = self._rand_choice(groups)
                        expr = template_str.format(g=param)
                    else:
                        expr = template_str
                    
                    if expr and expr not in strategies:
                        # 检查模板安全性
                        if field_in_template and not self._is_template_safe(field_in_template, expr):
                            continue
                        
                        # 随机决定是否添加处理（使用较保守的概率）
                        expr = self._maybe_add_neutralization(expr, prob=0.15)  # 降低到15%
                        expr = self._maybe_add_smoothing(expr, prob=0.1)  # 降低到10%
                        
                        if expr and expr not in strategies:
                            strategies.append(expr)
                except:
                    continue
        else:
            # 固定模式：生成所有模板组合
            for template_info in template_pool:
                template_str, param_type, needs_field = template_info
                
                if param_type == 'window':
                    for param in windows:
                        expr = template_str.format(w=param)
                        if expr and expr not in strategies:
                            strategies.append(expr)
                elif param_type == 'delay':
                    for param in delays:
                        expr = template_str.format(d=param)
                        if expr and expr not in strategies:
                            strategies.append(expr)
                elif param_type == 'group':
                    for param in groups:
                        expr = template_str.format(g=param)
                        if expr and expr not in strategies:
                            strategies.append(expr)
                else:
                    if template_str and template_str not in strategies:
                        strategies.append(template_str)

        # 移除无效表达式
        strategies = [s for s in strategies if s and 'None' not in str(s)]
        return list(dict.fromkeys(strategies))[:count]

    def generate_cross_dataset_strategy(self, primary_fields: List[str], secondary_fields: List[str], count: int = 100) -> List[str]:
        """生成跨数据集组合策略"""
        strategies = []
        
        if not secondary_fields:
            return self.generate_basic_strategy(primary_fields, {}, count)
        
        # 构建跨数据集模板
        cross_templates = self._build_cross_dataset_templates(primary_fields, secondary_fields)
        
        if self.random_mode:
            # 随机选择
            sampled = self._rand_choice(cross_templates, k=min(count, len(cross_templates)))
            strategies = list(dict.fromkeys(sampled))
        else:
            # 所有组合
            strategies = list(dict.fromkeys(cross_templates))
        
        return strategies[:count]

    def generate_multi_factor_strategy(self, datafields: List[str], templates: dict, count: int = 100) -> List[str]:
        """生成多因子组合策略"""
        multi_templates = templates['multi_factor_strategies']['categories']
        strategies = []
        n = len(datafields)

        for i in range(0, n-1, 2):
            field1 = datafields[i]
            field2 = datafields[i+1]

            # 1. 回归中性化
            for strategy in multi_templates.get('1_回归中性化', {}).get('strategies', []):
                if 'expression_template' in strategy:
                    expression = strategy['expression_template'].format(field1=field1, field2=field2)
                    strategies.append(expression)

            # 2. 条件组合
            for strategy in multi_templates.get('2_条件组合', {}).get('strategies', []):
                if 'expression_template' in strategy:
                    expression = strategy['expression_template'].format(field1=field1, field2=field2)
                    strategies.append(expression)

            # 3. 复杂信号
            for strategy in multi_templates.get('3_复杂信号', {}).get('strategies', []):
                if 'expression_template' in strategy:
                    expression = strategy['expression_template'].format(field1=field1, field2=field2)
                    strategies.append(expression)

        # 移除None
        strategies = [s for s in strategies if s is not None]
        return strategies[:count] if count else strategies

    def list_categories(self, mode=1):
        """列出策略分类"""
        templates = self._load_templates()

        if mode == 1:
            categories = templates['basic_strategies']['categories']
        else:
            categories = templates['multi_factor_strategies']['categories']

        result = []
        for category_name, category_data in categories.items():
            result.append({
                'name': category_name,
                'description': category_data.get('description', ''),
                'count': len(category_data.get('strategies', []))
            })

        return result


# 测试
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    # 测试随机模式
    print("=== 随机模式（seed=42）===")
    alpha1 = AlphaStrategy(seed=42, random_mode=True)
    results1 = alpha1.generate_basic_strategy(['returns', 'volume', 'close'], {}, count=10)
    for i, s in enumerate(results1, 1):
        print(f"{i}. {s}")

    print("\n=== 随机模式（seed=100）===")
    alpha2 = AlphaStrategy(seed=100, random_mode=True)
    results2 = alpha2.generate_basic_strategy(['returns', 'volume', 'close'], {}, count=10)
    for i, s in enumerate(results2, 1):
        print(f"{i}. {s}")

    print("\n=== 固定模式 ===")
    alpha3 = AlphaStrategy(random_mode=False)
    results3 = alpha3.generate_basic_strategy(['returns'], {}, count=10)
    for i, s in enumerate(results3, 1):
        print(f"{i}. {s}")
