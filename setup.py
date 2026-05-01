from setuptools import setup, find_packages

setup(
    name="server-monitor",
    version="1.0.3",
    author="KJAYDev",
    author_email="jakelenjalen@gmail.com",
    description="A professional cross-platform server monitoring dashboard with a desktop GUI.",
    long_description=open("README.md").read() if hasattr(open, "README.md") else "",
    long_description_content_type="text/markdown",
    url="https://github.com/jakelen61732/server_monitor",
    project_urls={
        "Bug Tracker": "https://github.com/jakelen61732/server_monitor/issues",
        "Source Code": "https://github.com/jakelen61732/server_monitor",
    },
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "flask>=3.0.0",
        "flask-socketio>=5.3.0",
        "gevent>=24.0.0",
        "gevent-websocket>=0.10.1",
        "waitress>=3.0.0",
        "psutil>=6.0.0",
        "gputil>=1.4.0",
        "pywebview>=5.0.0",
        "pyghmi>=1.6.15",
        "pythonnet>=3.0.3"
    ],
    python_requires=">=3.7",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: System Administrators",
        "Topic :: System :: Monitoring",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
