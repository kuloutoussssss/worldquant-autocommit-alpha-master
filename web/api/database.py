# -*- coding: utf-8 -*-
"""
Database API
"""
import sys
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query

from web.config import get_settings, PROJECT_ROOT
from web.api.schemas import AlphaListResponse, AlphaInfo
from web.api.tasks import load_tasks, save_tasks

router = APIRouter()
settings = get_settings()


@router.get("/alphas", response_model=AlphaListResponse)
async def get_alphas(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    status: Optional[str] = Query(None, description="Filter by status: all/submitted/pending/failed"),
    min_sharpe: Optional[float] = Query(None, ge=0),
    min_fitness: Optional[float] = Query(None, ge=0)
):
    """Get Alpha list with pagination"""
    sys.path.insert(0, str(PROJECT_ROOT))
    
    from core.db_manager import get_database
    
    db = get_database()
    
    # Build query conditions
    conditions = []
    params = []
    
    if status == "submitted":
        conditions.append("submitted_at IS NOT NULL")
    elif status == "pending":
        conditions.append("submitted_at IS NULL AND checks_passed = 1")
    elif status == "failed":
        conditions.append("submit_fail_count >= 3")
    
    if min_sharpe is not None:
        conditions.append("sharpe >= ?")
        params.append(min_sharpe)
    
    if min_fitness is not None:
        conditions.append("fitness >= ?")
        params.append(min_fitness)
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    with db._get_connection() as conn:
        # Get total count
        cursor = conn.execute(f"SELECT COUNT(*) FROM alphas WHERE {where_clause}", params)
        total = cursor.fetchone()[0]
        
        # Get paginated data
        offset = (page - 1) * page_size
        cursor = conn.execute(f"""
            SELECT alpha_id, expression, sharpe, fitness, turnover, returns, drawdown,
                   created_at, submitted_at, checks_passed, submit_fail_count
            FROM alphas
            WHERE {where_clause}
            ORDER BY fitness DESC, sharpe DESC
            LIMIT ? OFFSET ?
        """, params + [page_size, offset])
        
        alphas = []
        for row in cursor.fetchall():
            alphas.append(AlphaInfo(
                alpha_id=row[0],
                expression=row[1],
                sharpe=row[2],
                fitness=row[3],
                turnover=row[4],
                returns=row[5],
                drawdown=row[6],
                created_at=row[7],
                submitted_at=row[8],
                checks_passed=bool(row[9]),
                submit_fail_count=row[10] or 0
            ))
    
    return AlphaListResponse(
        success=True,
        alphas=alphas,
        total=total
    )


@router.get("/alphas/{alpha_id}")
async def get_alpha(alpha_id: str):
    """Get single Alpha details"""
    sys.path.insert(0, str(PROJECT_ROOT))
    
    from core.db_manager import get_database
    
    db = get_database()
    alpha = db.get_alpha(alpha_id)
    
    if not alpha:
        raise HTTPException(status_code=404, detail=f"Alpha {alpha_id} not found")
    
    return {
        "success": True,
        "alpha": alpha
    }


@router.delete("/alphas/{alpha_id}")
async def delete_alpha(alpha_id: str):
    """Delete Alpha"""
    sys.path.insert(0, str(PROJECT_ROOT))
    
    from core.db_manager import get_database
    
    db = get_database()
    success = db.delete_alpha(alpha_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Alpha {alpha_id} not found")
    
    return {
        "success": True,
        "message": f"Alpha {alpha_id} deleted"
    }


@router.get("/stats")
async def get_stats():
    """Get database statistics"""
    sys.path.insert(0, str(PROJECT_ROOT))
    
    from core.db_manager import get_database
    
    db = get_database()
    
    with db._get_connection() as conn:
        # Total count
        cursor = conn.execute("SELECT COUNT(*) FROM alphas")
        total = cursor.fetchone()[0]
        
        # Submitted
        cursor = conn.execute("SELECT COUNT(*) FROM alphas WHERE submitted_at IS NOT NULL")
        submitted = cursor.fetchone()[0]
        
        # Qualified but not submitted
        cursor = conn.execute("""
            SELECT COUNT(*) FROM alphas 
            WHERE sharpe >= 1.25 AND fitness >= 1.0 AND turnover <= 0.70 
            AND submitted_at IS NULL
        """)
        qualified = cursor.fetchone()[0]
        
        # Failed
        cursor = conn.execute("SELECT COUNT(*) FROM alphas WHERE submit_fail_count >= 3")
        failed = cursor.fetchone()[0]
        
        # Average metrics
        cursor = conn.execute("""
            SELECT AVG(sharpe), AVG(fitness), AVG(turnover)
            FROM alphas WHERE sharpe IS NOT NULL
        """)
        avg_metrics = cursor.fetchone()
    
    return {
        "success": True,
        "stats": {
            "total": total,
            "submitted": submitted,
            "qualified": qualified,
            "failed": failed,
            "avg_sharpe": round(avg_metrics[0] or 0, 3),
            "avg_fitness": round(avg_metrics[1] or 0, 3),
            "avg_turnover": round(avg_metrics[2] or 0, 3)
        }
    }


@router.post("/cleanup")
async def cleanup_database():
    """Cleanup database"""
    sys.path.insert(0, str(PROJECT_ROOT))
    
    from core.db_manager import get_database
    import json
    
    db = get_database()
    
    # Delete records with submit_fail_count >= 5
    with db._get_connection() as conn:
        cursor = conn.execute("DELETE FROM alphas WHERE submit_fail_count >= 5")
        deleted = cursor.rowcount
        conn.commit()
    
    # Cleanup orphaned data
    orphaned_files_cleaned = 0
    
    return {
        "success": True,
        "message": f"Cleanup completed",
        "deleted": deleted,
        "orphaned_files_cleaned": orphaned_files_cleaned
    }
