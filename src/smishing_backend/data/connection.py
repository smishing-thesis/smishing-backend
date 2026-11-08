from sqlalchemy import Engine, create_engine


def create_database_engine(url: str) -> Engine:
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True, echo=False)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        raise ValueError("PostgreSQL is required")
    return engine
