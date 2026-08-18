# scripts/dev/init_knowledge_db.py
from hermes.knowledge.db import create_db_and_tables

def main():
    print("Initializing knowledge base...")
    create_db_and_tables()
    print("Knowledge base initialized successfully.")

if __name__ == "__main__":
    main()
