# Scraper Engine Management

This document explains the new scraper engine abstraction system.

## Overview

The scraper engine configuration has been abstracted into a dedicated `scraper_engines.py` module to improve maintainability and organization. This separation allows for:

- Centralized engine configuration management
- Easy addition of new tenants
- Consistent fallback strategies
- Better testing and debugging capabilities

## Architecture

### ScraperEngineManager

The `ScraperEngineManager` class handles all engine configuration logic:

```python
from property.scraper_engines import ScraperEngineManager

# Get engines for a tenant
engines = ScraperEngineManager.get_engines_for_tenant('corcoran_group')

# Get tenant configuration summary
summary = ScraperEngineManager.get_tenant_summary('corcoran_group')
```

### Default Engine Order

The default fallback engine order is defined in `DEFAULT_FALLBACK_ENGINES`:

```python
DEFAULT_FALLBACK_ENGINES = [Compass, ColdwellBanker, Zillow, Corcoran]
```

This order is used as the base for all tenant configurations.

### Tenant Configuration

Each tenant can have a custom configuration in `TENANT_ENGINE_CONFIG`:

```python
TENANT_ENGINE_CONFIG = {
    'corcoran_group': {
        'primary': Corcoran, 
        'fallback_count': 3,
        'description': 'Corcoran Group tenant with Corcoran engine first'
    },
    # ... other tenants
}
```

## Usage Examples

### Adding a New Tenant

```python
# Method 1: Add to TENANT_ENGINE_CONFIG dictionary
TENANT_ENGINE_CONFIG['new_tenant'] = {
    'primary': SomeEngine,
    'fallback_count': 2,
    'description': 'New tenant configuration'
}

# Method 2: Use the helper method
ScraperEngineManager.add_tenant_config(
    tenant_id='new_tenant',
    primary_engine=SomeEngine,
    fallback_count=2,
    description='New tenant configuration'
)
```

### Changing Default Engine Order

```python
# Update the default order
new_order = [Zillow, Compass, ColdwellBanker, Corcoran]
ScraperEngineManager.update_default_engine_order(new_order)
```

### Getting Engine Information

```python
# Get engines for a tenant
engines = ScraperEngineManager.get_engines_for_tenant('daniel_gale')

# Get detailed summary
summary = ScraperEngineManager.get_tenant_summary('daniel_gale')
print(summary)
# Output:
# {
#     'tenant_id': 'daniel_gale',
#     'engines': ['DanielGale', 'Compass', 'ColdwellBanker', 'Zillow'],
#     'engine_count': 4,
#     'primary_engine': 'DanielGale',
#     'fallback_engines': ['Compass', 'ColdwellBanker', 'Zillow'],
#     'has_custom_config': True,
#     'config': {...}
# }
```

## PropertyManager Integration

The `PropertyManager` now uses `ScraperEngineManager` for all engine-related operations:

```python
class PropertyManager():
    def __init__(self, address: str, tenant_id: str = "editora", ...):
        # Get engines from ScraperEngineManager
        self.engines = ScraperEngineManager.get_engines_for_tenant(tenant_id)
        # ... rest of initialization
    
    def get_engine_summary(self) -> dict:
        return get_tenant_engine_summary(self.tenant_id)
```

## Benefits

1. **Separation of Concerns**: Engine configuration is separate from property management logic
2. **Maintainability**: Easy to add/modify tenant configurations
3. **Consistency**: Standardized fallback behavior across all tenants
4. **Testability**: Engine configuration can be tested independently
5. **Flexibility**: Runtime configuration changes are possible
6. **Documentation**: Clear structure makes the system easier to understand

## Migration Notes

- All engine configuration logic moved from `PropertyManager` to `ScraperEngineManager`
- `PropertyManager` now focuses solely on property data extraction
- Backward compatibility maintained through convenience functions
- No changes required to existing `PropertyManager` usage

## Testing

Run the test script to verify configurations:

```bash
python test_scraper_engines.py
```

This will show all tenant configurations and verify engine instantiation works correctly.
