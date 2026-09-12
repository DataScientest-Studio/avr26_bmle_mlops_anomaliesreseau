import hmac
import hashlib
from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

from src.config.settings import settings

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="user")

    def __repr__(self) -> str:
        return f"<User(user_id={self.user_id}, username='{self.username}', role='{self.role}')>"

SECRET_KEY = "lvcnrM3FcRg5g+RspAYOd8GNA4C4hkrMKuAmNncJ6Vg="

def hash_password_hs256(password: str, secret: str = SECRET_KEY) -> str:
    """Génère une empreinte HMAC-SHA256 encodée en hexadécimal."""
    return hmac.new(
        secret.encode("utf-8"),
        password.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def init_and_seed_db():
    engine = create_engine(settings.sqlalchemy_url, echo=False)
    
    # 1. Création de la table
    Base.metadata.create_all(engine)
    print("Table 'users' vérifiée / créée.")

    # 2. Données initiales
    seed_users = [
        {"username": "admin", "password": "admin", "role": "admin"},
        {"username": "user123", "password": "password123", "role": "user"},
    ]

    # 3. Insertion via une session SQLAlchemy
    with Session(engine) as session:
        for user_data in seed_users:
            stmt = select(User).where(User.username == user_data["username"])
            existing_user = session.execute(stmt).scalar_one_or_none()

            if not existing_user:
                new_user = User(
                    username=user_data["username"],
                    password=hash_password_hs256(user_data["password"]),
                    role=user_data["role"],
                )
                session.add(new_user)
                print(f"Utilisateur '{user_data['username']}' inséré.")
            else:
                print(f"Utilisateur '{user_data['username']}' existe déjà (ignoré).")

        session.commit()

if __name__ == "__main__":
    init_and_seed_db()