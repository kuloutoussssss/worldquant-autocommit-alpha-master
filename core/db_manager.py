# -*- coding: utf-8 -*-
"""Alpha Database Manager - SQLite storage for Alpha data"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Set
from .logger import logger

DB_PATH = "data/alphas.db"
CANDIDATE_POOL_FILE = "data/alphas/candidate_pool.json"


class AlphaDatabase:
    """Alpha database management"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()
    
    def _get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def _init_tables(self):
        """初始化数据库表"""
        with self._get_connection() as conn:
            # 检查alphas表是否存在，如果不存在则创建
            cursor = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='alphas'
            """)
            if not cursor.fetchone():
                conn.execute("""
                    CREATE TABLE alphas (
                        alpha_id TEXT PRIMARY KEY,
                        expression TEXT NOT NULL,
                        sharpe REAL,
                        fitness REAL,
                        turnover REAL,
                        returns REAL,
                        drawdown REAL,
                        checks_passed INTEGER DEFAULT 0,
                        created_at TEXT,
                        updated_at TEXT,
                        submitted_at TEXT,
                        submit_fail_count INTEGER DEFAULT 0,
                        submit_fail_reason TEXT,
                        status TEXT DEFAULT 'active'
                    )
                """)
                # 创建索引加速候选池查询
                conn.execute("CREATE INDEX idx_candidates ON alphas(checks_passed, submitted_at, submit_fail_count)")
            else:
                # 如果表已存在，检查并添加新字段
                cursor = conn.execute("PRAGMA table_info(alphas)")
                existing_columns = [row[1] for row in cursor.fetchall()]
                
                if 'in_candidate_pool' not in existing_columns:
                    conn.execute("ALTER TABLE alphas ADD COLUMN in_candidate_pool INTEGER DEFAULT 0")
                if 'candidate_pool_time' not in existing_columns:
                    conn.execute("ALTER TABLE alphas ADD COLUMN candidate_pool_time TEXT")
                if 'submit_fail_count' not in existing_columns:
                    conn.execute("ALTER TABLE alphas ADD COLUMN submit_fail_count INTEGER DEFAULT 0")
                if 'submit_fail_reason' not in existing_columns:
                    conn.execute("ALTER TABLE alphas ADD COLUMN submit_fail_reason TEXT")

            # 检查sync_log表是否存在
            cursor = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='sync_log'
            """)
            if not cursor.fetchone():
                conn.execute("""
                    CREATE TABLE sync_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sync_time TEXT NOT NULL,
                        total_count INTEGER,
                        new_count INTEGER,
                        update_count INTEGER
                    )
                """)
            
            # 检查tested_expressions表是否存在（已回测表达式）
            cursor = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='tested_expressions'
            """)
            if not cursor.fetchone():
                conn.execute("""
                    CREATE TABLE tested_expressions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        expression TEXT NOT NULL UNIQUE,
                        alpha_id TEXT,
                        sharpe REAL,
                        fitness REAL,
                        turnover REAL,
                        returns REAL,
                        drawdown REAL,
                        self_corr REAL DEFAULT -1,
                        status TEXT DEFAULT 'OK',
                        test_time TEXT NOT NULL
                    )
                """)
                # 为 expression 列创建索引，加速查询
                conn.execute("CREATE INDEX IF NOT EXISTS idx_expression ON tested_expressions(expression)")
            else:
                # 如果表已存在，检查并添加 self_corr 字段
                cursor = conn.execute("PRAGMA table_info(tested_expressions)")
                existing_columns = [row[1] for row in cursor.fetchall()]
                if 'self_corr' not in existing_columns:
                    conn.execute("ALTER TABLE tested_expressions ADD COLUMN self_corr REAL DEFAULT -1")
            
            conn.commit()
    
    def has_data(self) -> bool:
        """Check if database has data"""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM alphas")
            return cursor.fetchone()[0] > 0
    
    def get_last_sync_time(self) -> Optional[datetime]:
        """Get last sync time"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT sync_time FROM sync_log ORDER BY id DESC LIMIT 1"
            )
            row = cursor.fetchone()
            return datetime.fromisoformat(row[0]) if row else None
    
    def _parse_checks_passed(self, alpha: Dict) -> int:
        """从Alpha的is.checks字段解析是否通过所有检查
        
        WorldQuant Brain的checks包括:
        - LOW_SHARPE: sharpe >= 1.25 才 PASS
        - LOW_FITNESS: fitness >= 1.0 才 PASS
        - LOW_TURNOVER: turnover >= 0.01 才 PASS
        - HIGH_TURNOVER: turnover <= 0.7 才 PASS
        - CONCENTRATED_WEIGHT: 权重不能过度集中
        - LOW_SUB_UNIVERSE_SHARPE: 子宇宙夏普率检查
        - SELF_CORRELATION: 自相关检查
        - MATCHES_COMPETITION: 必须匹配比赛
        
        只有所有check都是PASS才算通过
        PENDING状态的check不算失败，需要等待完成
        """
        is_data = alpha.get('is') or {}
        checks = is_data.get('checks') or []
        
        # 所有必需的 checks 必须全部 PASS (暂时忽略 SELF_CORRELATION)
        required_checks = {
            'LOW_SHARPE',              # sharpe >= 1.25
            'LOW_FITNESS',             # fitness >= 1.0
            'LOW_TURNOVER',            # turnover >= 0.01
            'HIGH_TURNOVER',           # turnover <= 0.7
            'CONCENTRATED_WEIGHT',     # 权重集中度检查
            'LOW_SUB_UNIVERSE_SHARPE', # 子宇宙夏普率检查
            # 'SELF_CORRELATION',       # 自相关检查 - 暂时忽略
            'MATCHES_COMPETITION'      # 必须匹配比赛
        }
        passed = set()
        pending = set()
        failed = set()
        
        for check in checks:
            name = check.get('name')
            result = check.get('result')
            if result == 'PASS':
                passed.add(name)
            elif result == 'PENDING':
                pending.add(name)
            elif result == 'FAIL':
                failed.add(name)
        
        # 调试日志：打印API返回的实际checks（只对前2个Alpha打印）
        if not hasattr(self, '_debug_count'):
            self._debug_count = 0
        self._debug_count += 1
        
        alpha_id = alpha.get('alpha_id') or alpha.get('id', 'unknown')
        if self._debug_count <= 2:
            if not checks:
                print(f"[DEBUG] [{alpha_id}] No checks returned from API")
            else:
                check_summary = ', '.join([f"{c.get('name')}:{c.get('result')}" for c in checks])
                print(f"[DEBUG] [{alpha_id}] Checks: {check_summary}")
            
        # 如果有任何必需check是FAIL，返回0
        if required_checks & failed:
            return 0
        
        # 如果有任何必需check是PENDING，返回-1（待定，需要等待）
        if required_checks & pending:
            return -1
        
        # 所有必需check都通过才算通过
        if required_checks.issubset(passed):
            return 1
        return 0

    def save_alphas(self, alphas: List[Dict], is_full_sync: bool = False) -> tuple:
        """Save Alpha data, returns (new_count, update_count)"""
        new_count = 0
        update_count = 0
        
        with self._get_connection() as conn:
            for alpha in alphas:
                alpha_id = alpha.get('alpha_id') or alpha.get('id')
                if not alpha_id:
                    continue
                
                cursor = conn.execute(
                    "SELECT 1 FROM alphas WHERE alpha_id = ?", (alpha_id,)
                )
                exists = cursor.fetchone() is not None
                
                now = datetime.now().isoformat()
                checks_passed = self._parse_checks_passed(alpha)
                
                # 从API数据提取metrics
                is_data = alpha.get('is') or {}
                sharpe = is_data.get('sharpe')
                fitness = is_data.get('fitness')
                turnover = is_data.get('turnover')
                returns = is_data.get('returns')
                drawdown = is_data.get('drawdown')
                
                # 处理expression字段，可能是字符串或字典
                regular_val = alpha.get('regular')
                if isinstance(regular_val, dict):
                    expression = regular_val.get('text', '') or regular_val.get('code', '')
                elif isinstance(regular_val, str):
                    expression = regular_val
                else:
                    expression = alpha.get('expression', '') or ''
                
                if exists:
                    conn.execute("""
                        UPDATE alphas SET
                            expression = ?, sharpe = ?, fitness = ?,
                            turnover = ?, returns = ?, drawdown = ?,
                            checks_passed = ?, updated_at = ?, status = 'active'
                        WHERE alpha_id = ?
                    """, (
                        expression, sharpe, fitness,
                        turnover, returns, drawdown,
                        checks_passed, now, alpha_id
                    ))
                    update_count += 1
                else:
                    conn.execute("""
                        INSERT INTO alphas
                        (alpha_id, expression, sharpe, fitness, turnover,
                         returns, drawdown, checks_passed, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        alpha_id, expression, sharpe, fitness,
                        turnover, returns, drawdown,
                        checks_passed, now, now
                    ))
                    new_count += 1
            
            conn.commit()
        
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO sync_log (sync_time, total_count, new_count, update_count)
                VALUES (?, ?, ?, ?)
            """, (datetime.now().isoformat(), len(alphas), new_count, update_count))
            conn.commit()
        
        logger.info(f"Saved alphas: {new_count} new, {update_count} updated")
        return new_count, update_count
    
    def get_submittable_alphas(self, exclude_today_submitted: bool = True) -> List[Dict]:
        """Get submittable alphas - 基于checks_passed筛选
        
        只有通过WorldQuant Brain官方checks验证的Alpha才会被返回:
        - LOW_SHARPE: sharpe >= 1.25
        - LOW_FITNESS: fitness >= 1.0
        - HIGH_TURNOVER: turnover <= 0.7
        
        默认跳过所有已提交的Alpha（不管是什么时候提交的）
        """
        query = """
            SELECT * FROM alphas
            WHERE checks_passed = 1
            AND submitted_at IS NULL
        """
        
        query += " ORDER BY fitness DESC, sharpe DESC"
        
        params = []
        
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            # 显式转换 sqlite3.Row 为字典，确保兼容性
            return [{k: row[k] for k in row.keys()} for row in cursor.fetchall()]
    
    def print_report(self):
        """打印数据库报告"""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM alphas")
            total = cursor.fetchone()[0]
            
            # 使用checks_passed字段统计
            cursor = conn.execute(
                "SELECT COUNT(*) FROM alphas WHERE checks_passed = 1"
            )
            qualified = cursor.fetchone()[0]
            
            cursor = conn.execute(
                "SELECT COUNT(*) FROM alphas WHERE submitted_at IS NOT NULL"
            )
            submitted = cursor.fetchone()[0]
            
            last_sync = self.get_last_sync_time()
            
            print("\n=== Alpha 数据库报告 ===")
            print(f"  Alpha总数: {total}")
            print(f"  通过Checks验证: {qualified}")
            print(f"  已提交: {submitted}")
            if last_sync:
                print(f"  最后同步: {last_sync.strftime('%Y-%m-%d %H:%M')}")
    
    def mark_submitted(self, alpha_id: str) -> bool:
        """标记Alpha已提交"""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE alphas SET submitted_at = ?, submit_fail_count = 0, submit_fail_reason = NULL
                    WHERE alpha_id = ?
                """, (datetime.now().isoformat(), alpha_id))
                conn.commit()
            logger.info(f"Marked alpha {alpha_id} as submitted")
            # 从候选池移除
            self._remove_from_candidate_pool(alpha_id)
            return True
        except Exception as e:
            logger.error(f"Failed to mark submitted: {e}")
            return False
    
    def mark_submit_failed(self, alpha_id: str, reason: str = "Unknown") -> bool:
        """标记Alpha提交失败
        
        Args:
            alpha_id: Alpha ID
            reason: 失败原因（从提交API响应中提取）
        
        Returns:
            True 表示继续保留候选池
            False 表示应该从候选池移除（失败次数过多）
        """
        try:
            with self._get_connection() as conn:
                # 获取当前失败次数
                cursor = conn.execute(
                    "SELECT submit_fail_count FROM alphas WHERE alpha_id = ?",
                    (alpha_id,)
                )
                row = cursor.fetchone()
                current_count = row[0] if row else 0
                new_count = current_count + 1
                
                # 更新失败记录
                conn.execute("""
                    UPDATE alphas SET submit_fail_count = ?, submit_fail_reason = ?
                    WHERE alpha_id = ?
                """, (new_count, reason, alpha_id))
                conn.commit()
            
            if new_count >= 3:
                logger.warning(f"Alpha {alpha_id} failed {new_count} times ({reason}), removing from candidate pool")
                self._remove_from_candidate_pool(alpha_id)
                return False
            else:
                logger.info(f"Alpha {alpha_id} submit failed ({reason}), count={new_count}/3")
                return True
        except Exception as e:
            logger.error(f"Failed to mark submit failed: {e}")
            return True  # 出错时保守处理，保留候选池

    def get_failed_expressions(self, min_fail_count: int = 1, limit: int = 100) -> List[Dict]:
        """获取提交失败的表达式及其失败原因
        
        Args:
            min_fail_count: 最少失败次数，默认1
            limit: 返回数量限制，默认100
        
        Returns:
            List[Dict]: 失败表达式列表，每项包含 expression, fail_count, fail_reason
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT expression, submit_fail_count, submit_fail_reason
                    FROM alphas
                    WHERE submit_fail_count >= ?
                    ORDER BY submit_fail_count DESC
                    LIMIT ?
                """, (min_fail_count, limit))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'expression': row[0],
                        'fail_count': row[1],
                        'fail_reason': row[2]
                    })
                return results
        except Exception as e:
            logger.error(f"Failed to get failed expressions: {e}")
            return []
    
    def reset_submit_failed(self, alpha_id: str) -> bool:
        """重置Alpha的提交失败计数，使其重新进入候选池
        
        Args:
            alpha_id: Alpha ID
        
        Returns:
            True if reset successful
        """
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE alphas SET submit_fail_count = 0, submit_fail_reason = NULL
                    WHERE alpha_id = ?
                """, (alpha_id,))
                conn.commit()
            logger.info(f"Alpha {alpha_id} reset to candidate pool")
            return True
        except Exception as e:
            logger.error(f"Failed to reset submit failed: {e}")
            return False

    # ========== 已回测表达式管理 ==========

    def is_expression_tested(self, expression: str) -> bool:
        """检查表达式是否已回测过"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM tested_expressions WHERE expression = ?",
                (expression,)
            )
            return cursor.fetchone() is not None

    def add_tested_expression(self, expression: str, alpha_id: str = None,
                              sharpe: float = None, fitness: float = None,
                              turnover: float = None, returns: float = None,
                              drawdown: float = None, self_corr: float = -1,
                              status: str = 'OK') -> bool:
        """添加已回测的表达式"""
        try:
            with self._get_connection() as conn:
                now = datetime.now().isoformat()
                conn.execute("""
                    INSERT OR IGNORE INTO tested_expressions 
                    (expression, alpha_id, sharpe, fitness, turnover, returns, drawdown, self_corr, status, test_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (expression, alpha_id, sharpe, fitness, turnover, returns, drawdown, self_corr, status, now))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add tested expression: {e}")
            return False

    def get_tested_count(self) -> int:
        """获取已回测表达式数量"""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM tested_expressions")
            return cursor.fetchone()[0]

    def update_self_corr(self, expression: str, self_corr: float) -> bool:
        """更新表达式的自相关系数"""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE tested_expressions SET self_corr = ?
                    WHERE expression = ?
                """, (self_corr, expression))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update self_corr: {e}")
            return False

    def get_tested_expressions(self) -> Set[str]:
        """获取所有已回测的表达式集合（用于批量回测过滤）"""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT expression FROM tested_expressions")
            return {row[0] for row in cursor.fetchall()}

    # ========== 候选池管理 ==========

    def _get_candidate_pool(self) -> List[Dict]:
        """获取候选池（内存中）"""
        path = Path(CANDIDATE_POOL_FILE)
        if not path.exists():
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load candidate pool: {e}")
            return []

    def _save_candidate_pool(self, pool: List[Dict]):
        """保存候选池到文件（向后兼容）"""
        path = Path(CANDIDATE_POOL_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(pool, f, ensure_ascii=False, indent=2)

    def _remove_from_candidate_pool(self, alpha_id: str):
        """从候选池移除Alpha（私有）- 同时更新文件和数据库"""
        # 更新文件（向后兼容）
        pool = self._get_candidate_pool()
        pool = [a for a in pool if a.get('alpha_id') != alpha_id]
        self._save_candidate_pool(pool)
        
        # 更新数据库字段
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE alphas SET in_candidate_pool = 0 WHERE alpha_id = ?
                """, (alpha_id,))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to update candidate pool in database: {e}")

    def remove_from_candidate_pool(self, alpha_id: str):
        """从候选池移除Alpha（公开，供外部调用）"""
        self._remove_from_candidate_pool(alpha_id)

    def get_candidates(self, limit: int = 100, offset: int = 0) -> tuple:
        """获取候选池 - checks_passed=1 且未提交的Alpha
        
        过滤条件:
        - checks_passed = 1
        - submitted_at IS NULL（未提交）
        - submit_fail_count < 3（失败次数不超过3次）
        
        Returns:
            tuple: (candidates, total_count)
        """
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            
            # 获取总数
            count_cursor = conn.execute("""
                SELECT COUNT(*) FROM alphas
                WHERE checks_passed = 1 
                  AND submitted_at IS NULL
                  AND (submit_fail_count IS NULL OR submit_fail_count < 3)
            """)
            total = count_cursor.fetchone()[0]
            
            # 获取分页数据
            cursor = conn.execute("""
                SELECT alpha_id, sharpe, fitness, turnover, returns, drawdown, created_at,
                       submit_fail_count, submit_fail_reason
                FROM alphas
                WHERE checks_passed = 1 
                  AND submitted_at IS NULL
                  AND (submit_fail_count IS NULL OR submit_fail_count < 3)
                ORDER BY fitness DESC, sharpe DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            # 显式转换 sqlite3.Row 为字典，确保兼容性
            candidates = [{k: row[k] for k in row.keys()} for row in cursor.fetchall()]
        
        return candidates, total

    def update_candidate_pool(self) -> int:
        """更新候选池 - 从数据库获取checks_passed=1的Alpha
        
        同时更新:
        1. candidate_pool.json 文件（向后兼容）
        2. alphas.in_candidate_pool 字段（新的单一数据源）
        """
        query = """
            SELECT alpha_id, sharpe, fitness, turnover, returns, drawdown, created_at
            FROM alphas
            WHERE checks_passed = 1
            ORDER BY fitness DESC, sharpe DESC
        """
        
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query)
            # 显式转换 sqlite3.Row 为字典，确保兼容性
            rows = [{k: row[k] for k in row.keys()} for row in cursor.fetchall()]
            
            # 更新数据库中的 in_candidate_pool 字段
            now = datetime.now().isoformat()
            
            # 先将所有 Alpha 的 in_candidate_pool 设为 0
            conn.execute("UPDATE alphas SET in_candidate_pool = 0")
            
            # 再将达标的设为 1
            for row in rows:
                conn.execute("""
                    UPDATE alphas SET in_candidate_pool = 1, candidate_pool_time = ?
                    WHERE alpha_id = ?
                """, (now, row['alpha_id']))
            
            conn.commit()
        
        # 保存到候选池文件（向后兼容）
        self._save_candidate_pool(rows)
        logger.info(f"Updated candidate pool with {len(rows)} candidates")
        return len(rows)

    def get_candidate_pool_count(self) -> int:
        """获取候选池数量"""
        candidates = self.get_candidates()
        return len(candidates)

    def get_pending_candidates(self) -> List[Dict]:
        """获取待定候选 - 有checks_passed=-1（pending checks）的Alpha"""
        query = """
            SELECT alpha_id, sharpe, fitness, turnover, returns, drawdown, created_at
            FROM alphas
            WHERE checks_passed = -1
            ORDER BY fitness DESC, sharpe DESC
        """
        
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query)
            # 显式转换 sqlite3.Row 为字典，确保兼容性
            return [{k: row[k] for k in row.keys()} for row in cursor.fetchall()]

    def get_pending_count(self) -> int:
        """获取待定状态的数量"""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM alphas WHERE checks_passed = -1")
            return cursor.fetchone()[0]

    def print_candidate_pool(self):
        """打印候选池状态"""
        with self._get_connection() as conn:
            # 总达标数（checks_passed=1）
            cursor = conn.execute("SELECT COUNT(*) FROM alphas WHERE checks_passed = 1")
            total_qualified = cursor.fetchone()[0]
            
            # 已提交数
            cursor = conn.execute("SELECT COUNT(*) FROM alphas WHERE submitted_at IS NOT NULL")
            submitted_count = cursor.fetchone()[0]
            
            # 可提交数（未提交且失败次数<3）
            cursor = conn.execute("""
                SELECT COUNT(*) FROM alphas 
                WHERE checks_passed = 1 AND submitted_at IS NULL 
                  AND (submit_fail_count IS NULL OR submit_fail_count < 3)
            """)
            submittable_count = cursor.fetchone()[0]
            
            # 待定数（pending）
            cursor = conn.execute("SELECT COUNT(*) FROM alphas WHERE checks_passed = -1")
            pending_count = cursor.fetchone()[0]
            
            # 失败次数>=3的Alpha数量
            cursor = conn.execute("""
                SELECT COUNT(*) FROM alphas 
                WHERE checks_passed = 1 AND submitted_at IS NULL AND submit_fail_count >= 3
            """)
            failed_count = cursor.fetchone()[0]
            
            # 前5个候选
            cursor = conn.execute("""
                SELECT alpha_id, fitness, sharpe, submit_fail_count FROM alphas 
                WHERE checks_passed = 1 AND submitted_at IS NULL
                  AND (submit_fail_count IS NULL OR submit_fail_count < 3)
                ORDER BY fitness DESC, sharpe DESC LIMIT 5
            """)
            top_candidates = cursor.fetchall()
        
        print("\n=== 候选池状态 ===")
        print(f"  达标Alpha总数: {total_qualified}")
        print(f"  已提交: {submitted_count}")
        print(f"  可提交: {submittable_count}")
        print(f"  失败移除: {failed_count}")
        print(f"  待定(pending): {pending_count}")
        
        if top_candidates:
            print(f"\n  前5个候选Alpha:")
            for i, row in enumerate(top_candidates, 1):
                fail_info = f", Failed={row[3]}" if row[3] else ""
                print(f"    {i}. {row[0]}: "
                      f"Fitness={row[1]:.2f}, "
                      f"Sharpe={row[2]:.2f}{fail_info}")


    # ========== 批量导入历史结果 ==========

    def import_batch_results(self, file_path: str) -> int:
        """从 batch_results.json 导入已回测结果
        
        返回导入数量
        """
        import json
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"Batch results file not found: {file_path}")
            return 0
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # batch_results.json 结构: {"result": "", "total": 2000, "qualified_count": 0, "results": [...]}
            # all_results_*.json 结构: {"results": [...]}
            if isinstance(data, dict):
                if 'results' in data:
                    results = data['results']
                elif isinstance(data.get('result'), list):
                    results = data['result']
                else:
                    results = []
            else:
                results = data if isinstance(data, list) else []
            
            count = 0
            for result in results:
                expression = result.get('expression', '')
                if not expression:
                    continue
                
                self.add_tested_expression(
                    expression=expression,
                    alpha_id=result.get('alpha_id'),
                    sharpe=result.get('sharpe'),
                    fitness=result.get('fitness'),
                    turnover=result.get('turnover'),
                    returns=result.get('returns'),
                    drawdown=result.get('drawdown'),
                    status='OK' if result.get('alpha_id') else 'NO_ALPHA_ID'
                )
                count += 1
            
            logger.info(f"Imported {count} results from {path.name}")
            return count
        except Exception as e:
            logger.error(f"Failed to import batch results: {e}")
            return 0

    def import_all_results(self, file_path: str) -> int:
        """从 all_results_*.json 导入已回测结果（包含错误信息）
        
        返回导入数量
        """
        import json
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"All results file not found: {file_path}")
            return 0
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # batch_results.json 结构: {"result": "", "total": 2000, "qualified_count": 0, "results": [...]}
            # all_results_*.json 结构: {"results": [...]}
            if isinstance(data, dict):
                if 'results' in data:
                    results = data['results']
                elif isinstance(data.get('result'), list):
                    results = data['result']
                else:
                    results = []
            else:
                results = data if isinstance(data, list) else []
            
            count = 0
            for result in results:
                expression = result.get('expression', '')
                if not expression:
                    continue
                
                # 判断是否成功
                is_error = 'error' in result or 'status_code' in result
                if is_error:
                    error_msg = result.get('error', '')[:200]
                    status = f"ERROR: {error_msg}"
                else:
                    status = 'OK' if result.get('alpha_id') else 'NO_ALPHA_ID'
                
                self.add_tested_expression(
                    expression=expression,
                    alpha_id=result.get('alpha_id'),
                    sharpe=result.get('sharpe'),
                    fitness=result.get('fitness'),
                    turnover=result.get('turnover'),
                    returns=result.get('returns'),
                    drawdown=result.get('drawdown'),
                    status=status
                )
                count += 1
            
            logger.info(f"Imported {count} results from {path.name}")
            return count
        except Exception as e:
            logger.error(f"Failed to import all results: {e}")
            return 0

    def migrate_results_directory(self, results_dir: str = "data/results") -> dict:
        """迁移 results 目录下所有 JSON 文件到数据库
        
        返回迁移统计 {"batch_results": count, "all_results": count}
        """
        results_path = Path(results_dir)
        if not results_path.exists():
            logger.warning(f"Results directory not found: {results_dir}")
            return {"batch_results": 0, "all_results": 0}
        
        stats = {"batch_results": 0, "all_results": 0}
        
        # 导入 batch_results.json
        batch_file = results_path / "batch_results.json"
        if batch_file.exists():
            stats["batch_results"] = self.import_batch_results(str(batch_file))
        
        # 导入 all_results_*.json
        for result_file in results_path.glob("all_results_*.json"):
            stats["all_results"] += self.import_all_results(str(result_file))
        
        return stats

    def cleanup_duplicate_tested_expressions(self) -> int:
        """清理 tested_expressions 表中的重复表达式（保留最新）
        
        返回删除的重复记录数
        """
        with self._get_connection() as conn:
            # 查找重复的表达式
            cursor = conn.execute("""
                SELECT expression, COUNT(*) as cnt, MAX(id) as max_id
                FROM tested_expressions
                GROUP BY expression
                HAVING cnt > 1
            """)
            duplicates = cursor.fetchall()
            
            deleted = 0
            for expr, cnt, max_id in duplicates:
                # 删除除最新外的所有记录
                conn.execute("""
                    DELETE FROM tested_expressions
                    WHERE expression = ? AND id < ?
                """, (expr, max_id))
                deleted += cnt - 1
            
            conn.commit()
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} duplicate tested expressions")
            return deleted


_db_instance = None

def get_database(db_path: str = DB_PATH):
    """Get database singleton"""
    global _db_instance
    if _db_instance is None:
        _db_instance = AlphaDatabase(db_path)
    return _db_instance
