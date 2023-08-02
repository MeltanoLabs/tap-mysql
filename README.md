# tap-mysql

`tap-mysql` is a Singer tap for mysql.

Built with the [Meltano Tap SDK](https://sdk.meltano.com) for Singer Taps.

## Installation

Install from GitHub:

```bash
pipx install git+https://github.com/MeltanoLabs/tap-mysql.git@main
```

## Configuration

### Accepted Config Options

| Setting             | Required | Default | Description |
|:--------------------|:--------:|:-------:|:------------|
| host                | False    | None    | Hostname for mysql instance. Note if sqlalchemy_url is set this will be ignored. |
| port                | False    |    3306 | The port on which mysql is awaiting connection. Note if sqlalchemy_url is set this will be ignored. |
| user                | False    | None    | User name used to authenticate. Note if sqlalchemy_url is set this will be ignored. |
| password            | False    | None    | Password used to authenticate. Note if sqlalchemy_url is set this will be ignored. |
| database            | False    | None    | Database name. Note if sqlalchemy_url is set this will be ignored. |
| sqlalchemy_url      | False    | None    | Example mysql://[username]:[password]@localhost:3306/[db_name] |
| stream_maps         | False    | None    | Config object for stream maps capability. For more information check out [Stream Maps](https://sdk.meltano.com/en/latest/stream_maps.html). |
| stream_map_config   | False    | None    | User-defined config values to be used within map expressions. |
| flattening_enabled  | False    | None    | 'True' to enable schema flattening and automatically expand nested properties. |
| flattening_max_depth| False    | None    | The max depth to flatten schemas. |
| batch_config        | False    | None    |             |


A full list of supported settings and capabilities for this
tap is available by running:

```bash
tap-mysql --about
```

### Configure using environment variables

This Singer tap will automatically import any environment variables within the working directory's
`.env` if the `--config=ENV` is provided, such that config values will be considered if a matching
environment variable is set either in the terminal context or in the `.env` file.

## Usage

You can easily run `tap-mysql` by itself or in a pipeline using [Meltano](https://meltano.com/).

### Executing the Tap Directly

```bash
tap-mysql --version
tap-mysql --help
tap-mysql --config CONFIG --discover > ./catalog.json
```

## Developer Resources

Follow these instructions to contribute to this project.

### Initialize your Development Environment

```bash
pipx install poetry
poetry install
```

### Create and Run Tests

Create tests within the `tests` subfolder and
  then run:

```bash
poetry run pytest
```

You can also test the `tap-mysql` CLI interface directly using `poetry run`:

```bash
poetry run tap-mysql --help
```

### Testing with [Meltano](https://www.meltano.com)

_**Note:** This tap will work in any Singer environment and does not require Meltano.
Examples here are for convenience and to streamline end-to-end orchestration scenarios._

Next, install Meltano (if you haven't already) and any needed plugins:

```bash
# Install meltano
pipx install meltano
# Initialize meltano within this directory
cd tap-mysql
meltano install
```

Now you can test and orchestrate using Meltano:

```bash
# Test invocation:
meltano invoke tap-mysql --version
# OR run a test `elt` pipeline:
meltano elt tap-mysql target-jsonl
```

### SDK Dev Guide

See the [dev guide](https://sdk.meltano.com/en/latest/dev_guide.html) for more instructions on how to use the SDK to
develop your own taps and targets.
