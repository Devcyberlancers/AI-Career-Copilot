import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8001,
        reload=True,
        reload_dirs=["app"],
        reload_excludes=[
            ".venv",
            ".venv/*",
            "node_modules",
            "node_modules/*",
            "uploads",
            "uploads/*",
            "generated_pdfs",
            "generated_pdfs/*",
        ],
    )
