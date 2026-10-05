"""
Setup script for Experience-Shaped Affective Agent (V0.9)
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="emotion_agent",
    version="0.9.0",
    author="Zhuyuyangyy",
    author_email="Zhuyuyangyy@users.noreply.github.com",
    description="Experience-Shaped Affective Agent with emotion-like functional modulation",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Zhuyuyangyy/emotion-like-functional-modulation",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Psychology",
    ],
    python_requires=">=3.8",
    install_requires=[
        "numpy>=1.24.0",
        "scikit-learn>=1.3.0",
        "matplotlib>=3.7.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=2.0",
            "black>=22.0",
            "flake8>=4.0",
            "mypy>=0.900",
        ],
    },
    test_suite="tests",
    include_package_data=True,
)
