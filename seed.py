import asyncio
import aiosqlite
from contexta.db.repositories import save_blueprint_version, activate_blueprint

async def seed_minimal_blueprint():
    async with aiosqlite.connect("./contexta.db") as conn:
        conn.row_factory = aiosqlite.Row
        
        # Save a basic blueprint
        bp = await save_blueprint_version(
            conn, 
            name="Alpha", 
            version="1.0.0", 
            prompt_text="You are a senior technical delivery manager."
        )
        
        # Activate it immediately
        await activate_blueprint(conn, bp.id)
        print(f"Seeded and activated: {bp.blueprint_name}")

asyncio.run(seed_minimal_blueprint())
