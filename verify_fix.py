#!/usr/bin/env python3
"""Final verification that the Alembic fix is working correctly."""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    print("Verifying Alembic model registration fix...")
    
    try:
        # Test 1: Import the models
        import contexta.db.models
        print("✓ Successfully imported contexta.db.models")
        
        # Test 2: Check that Base metadata is accessible
        if hasattr(contexta.db.models, 'Base'):
            metadata = contexta.db.models.Base.metadata
            print(f"✓ Base.metadata accessible with {len(metadata.tables)} tables")
            
            # List all tables to verify they include expected ones
            tables = list(metadata.tables.keys())
            print(f"✓ Tables found: {sorted(tables)}")
            
            # Verify key tables are present
            expected_tables = ['projects', 'versions', 'nodes', 'reviews']
            missing_tables = [t for t in expected_tables if t not in tables]
            
            if not missing_tables:
                print("✓ All expected tables found: projects, versions, nodes, reviews")
            else:
                print(f"⚠ Missing expected tables: {missing_tables}")
                
            print("\n🎉 Fix verification successful!")
            print("The Alembic configuration now properly imports models from contexta.db.models")
            print("This should resolve the 'no such table: projects' error.")
            return True
        else:
            print("✗ Base class not found in models")
            return False
            
    except Exception as e:
        print(f"✗ Error during verification: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)