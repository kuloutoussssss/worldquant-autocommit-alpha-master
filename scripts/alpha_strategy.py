# -*- coding: utf-8 -*-
"""
Alpha 策略生成模块

策略模板通过配置文件管理：
- 配置文件路径：data/templates/strategy_templates.json
- 修改配置文件即可添加新策略，无需修改代码
- 策略分类清晰：
  - 基础策略（单因子）：日内策略、波动率策略、成交量策略、市场微观结构、条件触发策略、精选策略
  - 多因子组合策略：回归中性化、条件组合、复杂信号、精选组合策略
"""
import json
from pathlib import Path


class AlphaStrategy:
    """Alpha 策略生成器"""
    
    def __init__(self):
        self.template_file = Path(__file__).parent.parent / "data" / "templates" / "strategy_templates.json"
        self._templates_cache = None

    def _load_templates(self):
        """加载策略模板配置文件"""
        if self._templates_cache is None:
            with open(self.template_file, 'r', encoding='utf-8') as f:
                self._templates_cache = json.load(f)
        return self._templates_cache

    def get_simulation_data(self, datafields, mode=1):
        """根据模式生成策略列表

        Args:
            datafields: 数据字段列表
            mode: 策略模式
                1 - 基础策略（单因子）
                2 - 多因子组合策略

        Returns:
            策略表达式列表
        """
        templates = self._load_templates()

        if mode == 1:
            return self.generate_basic_strategy(datafields, templates)
        elif mode == 2:
            return self.generate_multi_factor_strategy(datafields, templates)
        else:
            print("❌ 无效的策略模式")
            return []

    def generate_basic_strategy(self, datafields, templates):
        """生成基础策略（单因子策略）

        从配置文件读取模板，支持动态添加策略
        通过参数变体生成大量因子
        """
        basic_templates = templates['basic_strategies']['categories']
        strategies = []

        # 参数变体配置 - 用于生成多个因子变体
        windows = [5, 10, 20, 30, 60]  # 时间窗口
        neutralizations = ['subindustry', 'industry', 'sector', None]  # 中性化方式
        decay_values = [0, 5, 10, 15, 20, 30]  # decay 值

        for field in datafields:
            # 1. 日内策略 - 生成多个时间窗口变体
            for window in [5, 10, 20]:
                strategies.append(f"group_rank((close - delay(close, {window}))/delay(close, {window}), subindustry)")
                strategies.append(f"group_rank((close - delay(close, {window}))/delay(close, {window}), industry)")
            
            # 2. 波动率策略 - 生成多个窗口和参数变体
            for window in windows:
                strategies.append(f"ts_std_dev({field}, {window})")
                strategies.append(f"ts_mean({field}, {window})")
                strategies.append(f"ts_rank({field}, {window})")
                strategies.append(f"rank({field} / ts_mean({field}, {window}))")
                strategies.append(f"({field} - ts_mean({field}, {window})) / ts_std_dev({field}, {window})")
                strategies.append(f"power(ts_std_dev(abs({field}), {window}), 2) - power(ts_std_dev({field}, {window}), 2)")
                strategies.append(f"group_rank(std({field}, {window})/mean({field}, {window}) * (1/cap), subindustry)")
                strategies.append(f"group_neutralize(rank({field}), bucket(rank(cap), range='0.1,1,0.1'))")

            # 3. 成交量相关策略（使用 field 作为成交量代理）
            for window in [10, 20, 30]:
                strategies.append(f"ts_corr({field}, volume/sharesout, {window})")
                strategies.append(f"ts_mean({field}, {window}) / ts_mean({field}, {window*2})")

            # 4. 市场微观结构
            for window in [10, 20]:
                strategies.append(f"group_neutralize(power(rank({field} - group_mean({field}, 1, subindustry)), 3), bucket(rank(cap), range='0,1,0.1'))")
                strategies.append(f"group_rank(correlation({field}, volume/sharesout, {window}), subindustry)")
                strategies.append(f"group_rank(correlation({field}, returns, {window}), subindustry)")

            # 5. 条件触发策略
            for window in [10, 20, 30]:
                strategies.append(f"trade_when(ts_rank(ts_std_dev(returns, {window}), 252) < 0.9, {field}, -1)")
                strategies.append(f"trade_when(volume > mean(volume, {window}), {field}, -1)")

            # 6. 回归中性化变体
            for neut in [None, 'subindustry', 'industry']:
                if neut:
                    strategies.append(f"group_neutralize({field}, {neut})")
                    strategies.append(f"group_rank({field}, {neut})")
                else:
                    strategies.append(f"rank({field})")
                    strategies.append(f"{field}")

            # 7. 排名和分位数变体
            strategies.append(f"rank({field})")
            strategies.append(f"rank(-1 * {field})")
            strategies.append(f"if_else(rank({field}) > 0.5, 1, -1)")
            strategies.append(f"power(rank({field}), 2)")
            strategies.append(f"power(rank({field}), 0.5)")

            # 8. 延迟变体
            for delay in [1, 2, 3, 5, 10]:
                strategies.append(f"{field} - delay({field}, {delay})")
                strategies.append(f"delay({field}, {delay}) / {field}")

            # 9. 行业排名变体
            strategies.append(f"group_rank({field}, subindustry)")
            strategies.append(f"group_rank({field}, industry)")
            strategies.append(f"group_zscore({field}, subindustry)")
            strategies.append(f"group_zscore({field}, industry)")

            # 10. 与市场基准对比
            strategies.append(f"{field} / cap")
            strategies.append(f"group_neutralize({field} / cap, subindustry)")

        # 移除None值
        strategies = [s for s in strategies if s is not None]

        return strategies

    def generate_multi_factor_strategy(self, datafields, templates):
        """生成多因子组合策略

        从配置文件读取模板，支持动态添加策略
        """
        multi_templates = templates['multi_factor_strategies']['categories']
        strategies = []
        n = len(datafields)

        for i in range(0, n-1, 2):
            field1 = datafields[i]
            field2 = datafields[i+1]

            # 1. 回归中性化（需要替换字段）
            for strategy in multi_templates['1_回归中性化']['strategies']:
                if 'expression_template' in strategy:
                    expression = strategy['expression_template'].format(field1=field1, field2=field2)
                    strategies.append(expression)

            # 2. 条件组合（需要替换字段）
            for strategy in multi_templates['2_条件组合']['strategies']:
                if 'expression_template' in strategy:
                    expression = strategy['expression_template'].format(field1=field1, field2=field2)
                    strategies.append(expression)

            # 3. 复杂信号（需要替换字段）
            for strategy in multi_templates['3_复杂信号']['strategies']:
                if 'expression_template' in strategy:
                    expression = strategy['expression_template'].format(field1=field1, field2=field2)
                    strategies.append(expression)

        # 4. 精选组合策略（检查所需字段）
        for strategy in multi_templates['4_精选组合策略']['strategies']:
            required_fields = strategy.get('required_fields', [])
            if all(field in datafields for field in required_fields):
                strategies.append(strategy['expression'])

        # 移除None值
        strategies = [s for s in strategies if s is not None]

        return strategies

    def list_categories(self, mode=1):
        """列出策略分类（用于文档生成或调试）

        Args:
            mode: 策略模式（1=基础策略，2=多因子组合）

        Returns:
            分类信息列表
        """
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
