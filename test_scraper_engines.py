#!/usr/bin/env python3
"""
Test script to verify the ScraperEngineManager abstraction works correctly.
"""

import sys
import os

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from property.scraper_engines import ScraperEngineManager


def test_engine_configurations():
    """Test engine configurations for different tenants."""
    print("=== Scraper Engine Manager Test ===\n")
    
    # Test different tenant configurations
    test_tenants = [
        'corcoran_group', 
        'daniel_gale', 
        'editora', 
        'jenna_cooper_la',
        'compass',
        'zillow',
        'watson_salari_group',
        'unknown_tenant'
    ]
    
    print("Testing tenant configurations:")
    print("-" * 50)
    
    for tenant in test_tenants:
        try:
            summary = ScraperEngineManager.get_tenant_summary(tenant)
            print(f"✓ {tenant}:")
            print(f"  Engines: {summary['engines']}")
            print(f"  Primary: {summary['primary_engine']}")
            print(f"  Fallbacks: {summary['fallback_engines']}")
            print(f"  Custom config: {summary['has_custom_config']}")
            print()
        except Exception as e:
            print(f"✗ {tenant}: ERROR - {e}")
            print()
    
    print("\nDefault engine order:")
    print("-" * 30)
    default_engines = ScraperEngineManager.get_default_engines()
    print([engine.__class__.__name__ for engine in default_engines])
    
    print("\nConfigured tenants:")
    print("-" * 20)
    configured_tenants = ScraperEngineManager.get_configured_tenants()
    print(configured_tenants)
    
    print("\nAvailable engines:")
    print("-" * 18)
    available_engines = ScraperEngineManager.get_all_available_engines()
    print(available_engines)
    
    print("\n=== Test Complete ===")


def test_engine_creation():
    """Test that engines are properly instantiated."""
    print("\n=== Engine Instantiation Test ===")
    
    try:
        engines = ScraperEngineManager.get_engines_for_tenant('corcoran_group')
        print(f"✓ Successfully created {len(engines)} engines for corcoran_group")
        
        for i, engine in enumerate(engines):
            print(f"  {i+1}. {engine.__class__.__name__} - {type(engine)}")
            
    except Exception as e:
        print(f"✗ Error creating engines: {e}")
    
    print("=== Instantiation Test Complete ===")


if __name__ == "__main__":
    test_engine_configurations()
    test_engine_creation()
