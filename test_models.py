#!/usr/bin/env python3
"""Test script to verify that models are properly registered with SQLAlchemy."""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    # Import the models to test registration
    import contexta.db.models
    print("✓ Successfully imported contexta.db.models")
    
    # Check if Base is available
    if hasattr(contexta.db.models, 'Base'):
        print("✓ Found Base class in models")
        
        # Check if metadata is available
        if hasattr(contexta.db.models.Base, 'metadata'):
            print("✓ Found metadata in Base class")
            metadata = contexta.db.models.Base.metadata
            print(f"✓ Metadata has {len(metadata.tables)} tables")
            
            # List the tables
            for table_name in sorted(metadata.tables.keys()):
                print(f"  - {table_name}")
                
            # Check specifically for projects table
            if 'projects' in metadata.tables:
                print("✓ 'projects' table found in metadata")
            else:
                print("✗ 'projects' table NOT found in metadata")
                
        else:
            print("✗ No metadata found in Base class")
    else:
        print("✗ No Base class found in models")
        
except Exception as e:
    print(f"✗ Error importing models: {e}")
    import traceback
    traceback.print_exc()

print("\nTest completed.")