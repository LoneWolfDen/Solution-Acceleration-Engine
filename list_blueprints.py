import asyncio
import aiosqlite
from contexta.db.repositories import list_blueprints, activate_blueprint

async def activate_first_blueprint():
    async with aiosqlite.connect("./contexta.db") as conn:
        conn.row_factory = aiosqlite.Row
        blueprints = await list_blueprints(conn)
        if not blueprints:
            print("No blueprints in the DB at all! You might need to seed the database.")
            return
        
        # Activate the first one we find
        target_id = blueprints[0].id
        await activate_blueprint(conn, target_id)
        print(f"Successfully activated: {blueprints[0].blueprint_name}")

asyncio.run(activate_first_blueprint())
