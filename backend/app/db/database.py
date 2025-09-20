from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from geoalchemy2 import Geometry  # Для PostGIS типов

DATABASE_URL = "postgresql+asyncpg://Admin:Gleb@localhost:5432/drone_db"  # Измените на env

engine = create_async_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)

Base = declarative_base()

async def get_db():
    async with SessionLocal() as session:
        yield session