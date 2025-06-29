# Setup

This project uses Python 3.12.

Install dependencies:
```bash
make install-dependencies
```

Copy the example configuration:
```bash
cp config.example.py config.py
```
Edit `config.py` with your credentials.

Run the pipeline:
```bash
make -j all
```

Run tests before committing:
```bash
make test
```

For offline smoke tests:
```bash
TEST_MODE=1 PYTHONPATH=. make -B -j all
```
