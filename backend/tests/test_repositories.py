import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, transaction
from app.models import Role, User
from app.repositories import UserRepository


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Role.__table__, User.__table__, Base.metadata.tables["user_roles"]])
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(bind=engine, tables=[Base.metadata.tables["user_roles"], User.__table__, Role.__table__])


def test_create_read_update_delete_and_relationship(session_factory):
    with transaction(session_factory) as session:
        operator = Role(name="operator")
        user = User(email="operator@example.test", password_hash="not-a-real-password-hash", roles=[operator])
        UserRepository(session).add(user)
        user_id = user.id

    with transaction(session_factory) as session:
        repository = UserRepository(session)
        persisted = repository.get(user_id)
        assert persisted is not None
        assert persisted.roles[0].name == "operator"
        persisted.is_active = False

    with transaction(session_factory) as session:
        repository = UserRepository(session)
        persisted = repository.by_email("operator@example.test")
        assert persisted is not None and persisted.is_active is False
        repository.delete(persisted)

    with transaction(session_factory) as session:
        assert UserRepository(session).get(user_id) is None


def test_transaction_rolls_back_on_failure(session_factory):
    user_id = uuid.uuid4()
    with pytest.raises(RuntimeError):
        with transaction(session_factory) as session:
            session.add(User(id=user_id, email="rollback@example.test", password_hash="not-a-real-password-hash"))
            raise RuntimeError("rollback")
    with transaction(session_factory) as session:
        assert UserRepository(session).get(user_id) is None
