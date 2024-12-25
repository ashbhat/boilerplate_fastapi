# FastAPI Boilerplate

A production-ready FastAPI boilerplate with a clean project structure, configuration management, and testing setup.

## Features

- 🚀 FastAPI with CORS middleware
- 📁 Clean project structure
- ⚙️ Environment-based configuration
- 🔒 Ready for authentication
- 📝 Pydantic schemas
- ✅ Testing setup with pytest

## Project Structure

```
boilerplate_fastapi/
├── app/
│   ├── main.py          # FastAPI app with CORS middleware
│   ├── api/             # API routes
│   │   └── v1/         # Version 1 endpoints
│   ├── core/           # Core configurations
│   │   └── config.py   # Environment settings
│   └── schemas/        # Pydantic models
├── tests/              # Test suite
├── .env.example        # Example environment variables
└── pyproject.toml     # Poetry dependencies
```

## Getting Started

1. Clone the repository:
```bash
gh repo clone ashbhat/boilerplate_fastapi
cd boilerplate_fastapi
```

2. Install dependencies:
```bash
poetry install
```

3. Copy the environment file:
```bash
cp .env.example .env
```

4. Run the development server:
```bash
poetry run fastapi dev app/main.py
```

## Testing

Run the test suite:
```bash
poetry run pytest
```

## Contributing

1. Create a new branch
2. Make your changes
3. Run tests
4. Submit a pull request

## License

MIT
