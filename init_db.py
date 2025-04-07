from bot import Base, engine

def init_database():
    print("Creating database tables...")
    Base.metadata.create_all(engine)
    print("Database tables created successfully!")

if __name__ == "__main__":
    init_database()