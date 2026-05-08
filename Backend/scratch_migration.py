import asyncio
from sqlalchemy import text
from app.database import engine

async def run_migration():
    async with engine.begin() as conn:
        print("Creating server_folders table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS server_folders (
                id UUID PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                parent_id UUID REFERENCES server_folders(id),
                team_id UUID NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        print("Adding folder_id column to servers table...")
        try:
            await conn.execute(text("ALTER TABLE servers ADD COLUMN folder_id UUID REFERENCES server_folders(id)"))
        except Exception as e:
            if "already exists" in str(e):
                print("Column folder_id already exists.")
            else:
                print(f"Error adding column: {e}")
                
    print("Done.")

if __name__ == "__main__":
    asyncio.run(run_migration())
