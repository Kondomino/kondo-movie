from typing import Any, Dict, Type, List
from pydantic import BaseModel, create_model
import yaml
from pathlib import Path
import re

def load_yaml(file_path: str) -> dict:
    config_path = Path(file_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file '{file_path}' does not exist.")
    
    with config_path.open('r') as f:
        config_data = yaml.safe_load(f)
    
    if not isinstance(config_data, dict):
        raise ValueError("Configuration file must contain a YAML dictionary at the root.")
    
    return config_data

def interpolate_config(config: Dict[str, Any], parent_keys: list = None, visited=None) -> Dict[str, Any]:
    """
    Recursively interpolates variables in the config dictionary.
    
    :param config: The configuration dictionary.
    :param parent_keys: The hierarchy of keys leading to the current config.
    :param visited: A set to keep track of visited keys to prevent circular references.
    :return: The interpolated configuration dictionary.
    """
    if parent_keys is None:
        parent_keys = []
    if visited is None:
        visited = set()
    
    variable_pattern = re.compile(r'\$\{([^}]+)\}')
    
    def resolve_variable(var_name: str, current_config: Dict[str, Any]) -> Any:
        """
        Resolves the value of a variable given its name.
        Supports dot notation for nested keys.
        
        :param var_name: The name of the variable to resolve.
        :param current_config: The current configuration dictionary.
        :return: The value of the variable.
        """
        keys = var_name.split('.')
        value = current_config
        for key in keys:
            if key not in value:
                raise ValueError(f"Variable '{var_name}' not found in configuration.")
            value = value[key]
        return value
    
    if isinstance(config, dict):
        for key, value in config.items():
            if isinstance(value, str):
                # Find all ${VAR} patterns
                matches = variable_pattern.findall(value)
                for var in matches:
                    # Prevent circular references
                    if var in visited:
                        raise ValueError(f"Circular reference detected for variable '{var}'.")
                    
                    # Resolve the variable
                    var_value = resolve_variable(var, config)
                    
                    # If the variable itself contains placeholders, interpolate it first
                    if isinstance(var_value, str) and variable_pattern.search(var_value):
                        visited.add(var)
                        var_value = interpolate_config({'temp': var_value}, parent_keys + [key], visited)['temp']
                        visited.remove(var)
                    
                    # Replace the placeholder with the actual value
                    if not isinstance(var_value, (str, int, float)):
                        raise ValueError(f"Variable '{var}' is of unsupported type {type(var_value)} for interpolation.")
                    
                    value = value.replace(f"${{{var}}}", str(var_value))
                config[key] = value
            elif isinstance(value, dict):
                config[key] = interpolate_config(value, parent_keys + [key], visited)
            elif isinstance(value, list):
                config[key] = [
                    interpolate_config(item, parent_keys + [key], visited) if isinstance(item, dict) else item
                    for item in value
                ]
        return config
    elif isinstance(config, list):
        return [
            interpolate_config(item, parent_keys, visited) if isinstance(item, dict) else item
            for item in config
        ]
    else:
        return config

def generate_pydantic_model(
    model_name: str,
    data: Any,
    model_cache: Dict[str, Type[BaseModel]] = None
) -> Type[BaseModel]:
    """
    Recursively generates Pydantic models from a nested dictionary,
    handling lists appropriately.
    
    :param model_name: Name of the Pydantic model to create.
    :param data: The data to create the model from (dict, list, or primitive).
    :param model_cache: A cache to store already created models to handle recursion.
    :return: A Pydantic BaseModel subclass.
    """
    if model_cache is None:
        model_cache = {}
    
    if isinstance(data, dict):
        fields = {}
        for key, value in data.items():
            # Ensure the field name is a valid Python identifier
            field_name = key.replace('-', '_').replace(' ', '_')
            
            if isinstance(value, dict):
                # Create a nested model
                nested_model_name = f"{model_name}_{key.capitalize()}"
                if nested_model_name in model_cache:
                    nested_model = model_cache[nested_model_name]
                else:
                    nested_model = generate_pydantic_model(nested_model_name, value, model_cache)
                fields[field_name] = (nested_model, ...)
            elif isinstance(value, list):
                if len(value) > 0:
                    first_item = value[0]
                    if isinstance(first_item, dict):
                        # Assume all items in the list have the same structure
                        nested_model_name = f"{model_name}_{key.capitalize()}Item"
                        if nested_model_name in model_cache:
                            nested_model = model_cache[nested_model_name]
                        else:
                            nested_model = generate_pydantic_model(nested_model_name, first_item, model_cache)
                        fields[field_name] = (List[nested_model], ...)
                    else:
                        # List of primitives
                        elem_type = type(first_item)
                        fields[field_name] = (List[elem_type], ...)
                else:
                    # Empty list; use List[Any]
                    fields[field_name] = (List[Any], ...)
            else:
                # Primitive types
                fields[field_name] = (type(value), ...)
        
        # Create the Pydantic model
        model = create_model(model_name, **fields)
        model_cache[model_name] = model
        return model
    
    elif isinstance(data, list):
        if len(data) > 0 and isinstance(data[0], dict):
            # Create a model for list items
            nested_model_name = f"{model_name}Item"
            nested_model = generate_pydantic_model(nested_model_name, data[0], model_cache)
            return List[nested_model]
        else:
            # List of primitives
            return List[type(data[0])] if len(data) > 0 else List[Any]
    
    else:
        # For primitive types, return the type directly
        return type(data)

def generate_config_model(config_data: dict) -> Type[BaseModel]:
    """
    Generates the root Pydantic model for the configuration.
    
    :param config_data: The configuration data as a dictionary.
    :return: The root Pydantic model class.
    """
    root_model = generate_pydantic_model("AppConfig", config_data)
    return root_model

CONFIG_FILE_PATH = 'src/config/config.yaml'

# Load YAML configuration
config_data = load_yaml(CONFIG_FILE_PATH)

# Interpolate variables
interpolated_config = interpolate_config(config_data)

# Generate the root Pydantic model
AppConfigModel = generate_config_model(interpolated_config)

# Instantiate the model with interpolated configuration data
settings = AppConfigModel(**interpolated_config)
