from sqlalchemy import Column, Integer, String, ForeignKey, Float, DateTime, func
from sqlalchemy.sql.sqltypes import Boolean
from _meta._migrations.base import Base


class Sample(Base):
    __tablename__ = 'SampleTable'

    id = Column(Integer, primary_key=True, index=True)