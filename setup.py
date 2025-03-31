from setuptools import setup, find_packages

setup(
    name="pipebot",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi==0.109.2",
        "uvicorn==0.27.1",
        "python-multipart==0.0.9",
        "msal==1.32.0",
        "PyJWT==2.8.0",
        "python-dotenv==1.0.0"
    ],
) 