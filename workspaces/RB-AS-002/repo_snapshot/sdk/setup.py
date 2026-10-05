from setuptools import setup, find_packages

setup(
    name="agentshield",
    version="0.3.0",
    description="AgentShield SDK - Behavior-chain risk governance for multi-agent systems",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[],
    extras_require={
        "http": ["httpx>=0.24.0"],
        "all": ["httpx>=0.24.0"],
    },
)
