from sqlalchemy.orm import Query
from app.models.job import Job


def rank_jobs_for_user(query: Query) -> Query:
    return query.order_by(Job.match_score.is_(None), Job.match_score.desc(), Job.created_at.desc())
