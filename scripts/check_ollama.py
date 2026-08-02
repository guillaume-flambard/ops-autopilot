#!/usr/bin/env python3
"""
Ollama setup verification script.
Checks if Ollama is running and the required model is available.
"""

import requests
import sys
from config import settings


def check_ollama_connection():
    """Check if Ollama server is running."""
    try:
        response = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=5)
        if response.status_code == 200:
            print("✓ Ollama server is running")
            return True
        else:
            print(f"✗ Ollama server returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"✗ Cannot connect to Ollama at {settings.ollama_base_url}")
        print("  Make sure Ollama is running: ollama serve")
        return False
    except Exception as e:
        print(f"✗ Error checking Ollama: {e}")
        return False


def check_model_available():
    """Check if the required model is available."""
    try:
        response = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [model.get("name", "") for model in models]
            
            # Check if our model is available (with or without tag)
            required_model = settings.ollama_model.split(":")[0]  # Remove tag if present
            available = any(required_model in name for name in model_names)
            
            if available:
                print(f"✓ Model '{settings.ollama_model}' is available")
                return True
            else:
                print(f"✗ Model '{settings.ollama_model}' not found")
                print(f"  Available models: {', '.join(model_names)}")
                print(f"  Pull the model: ollama pull {settings.ollama_model}")
                return False
    except Exception as e:
        print(f"✗ Error checking model: {e}")
        return False


def test_model_generation():
    """Test that the model can generate text."""
    try:
        response = requests.post(
            f"{settings.ollama_base_url}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": "Say 'Hello, Ollama is working!'",
                "stream": False
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json().get("response", "")
            print(f"✓ Model generation test passed")
            print(f"  Response: {result[:100]}...")
            return True
        else:
            print(f"✗ Model generation failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error testing model generation: {e}")
        return False


def main():
    """Run all checks."""
    print("Ollama Setup Verification")
    print("=" * 50)
    print(f"Ollama URL: {settings.ollama_base_url}")
    print(f"Model: {settings.ollama_model}")
    print()
    
    checks = [
        check_ollama_connection,
        check_model_available,
        test_model_generation
    ]
    
    results = [check() for check in checks]
    
    print()
    print("=" * 50)
    if all(results):
        print("✓ All checks passed! Ollama is ready.")
        return 0
    else:
        print("✗ Some checks failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
