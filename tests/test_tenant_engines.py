#!/usr/bin/env python3
"""
Test script to verify tenant engine configurations
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.property_manager import PropertyManager
from logger import logger

def test_tenant_engines():
    """Test that all tenants have proper engine configurations"""
    
    # Define all expected tenants
    expected_tenants = [
        "editora",
        "jenna_cooper_la", 
        "daniel_gale",
        "coldwell_banker",
        "compass",
        "corcoran_group",
        "zillow",
        "watson_salari_group"
    ]
    
    print("🧪 Testing Tenant Engine Configurations")
    print("=" * 50)
    
    for tenant_id in expected_tenants:
        print(f"\n📋 Testing tenant: {tenant_id}")
        
        try:
            # Create PropertyManager instance
            property_mgr = PropertyManager(
                address="123 Test St, New York, NY 10001",
                tenant_id=tenant_id
            )
            
            # Get engines for this tenant
            engines = property_mgr._get_tenant_engines(tenant_id)
            
            # Print engine configuration
            print(f"   ✅ Engines configured: {len(engines)} engines")
            for i, engine in enumerate(engines, 1):
                engine_name = engine.__class__.__name__
                priority = "🥇 PRIMARY" if i == 1 else f"🔄 FALLBACK #{i-1}"
                print(f"      {priority}: {engine_name}")
            
            # Verify primary engine is appropriate for tenant
            primary_engine = engines[0].__class__.__name__
            expected_primary = {
                "jenna_cooper_la": "JennaCooperLA",
                "daniel_gale": "DanielGale", 
                "coldwell_banker": "ColdwellBanker",
                "compass": "Compass",
                "corcoran_group": "Corcoran",
                "zillow": "Zillow",
                "watson_salari_group": "Zillow",  # TODO: Should be WatsonSalariGroup when implemented
                "editora": "Compass"  # Default
            }
            
            if tenant_id in expected_primary:
                expected = expected_primary[tenant_id]
                if primary_engine == expected:
                    print(f"   ✅ Primary engine correct: {primary_engine}")
                else:
                    print(f"   ❌ Primary engine mismatch: expected {expected}, got {primary_engine}")
            else:
                print(f"   ⚠️  No expected primary engine defined for {tenant_id}")
                
        except Exception as e:
            print(f"   ❌ Error configuring tenant {tenant_id}: {str(e)}")
    
    print("\n" + "=" * 50)
    print("✅ Tenant engine configuration test completed!")

if __name__ == "__main__":
    test_tenant_engines()
