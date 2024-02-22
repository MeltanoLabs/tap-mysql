# tap-mysql

`tap-mysql` is a Singer tap for mysql.

Built with the [Meltano Tap SDK](https://sdk.meltano.com) for Singer Taps.

## Installation

Install from GitHub:

```bash
pipx install git+https://github.com/MeltanoLabs/tap-mysql.git@main
```

Note that you will also need to install the requisite dependencies for mysqlclient. Example installation command:

```bash
sudo apt-get update
sudo apt-get install package-cfg libmysqlclient-dev
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
| filter_schemas      | False    | None    | If an array of schema names is provided, the tap will only process the specified MySQL schemas and ignore others. If left blank, the tap automatically processes ALL available MySQL schemas. |
| sqlalchemy_options             | False    | None    | This needs to be passed in as a JSON Object. sqlalchemy_url options (also called the query), to connect to PlanetScale you must turn on SSL see PlanetScale information below. Note if sqlalchemy_url is set this will be ignored. |
| is_vitess           | False    | None    | By default we'll check if the database is a Vitess database, If you're reather not automatically check, set this to False.See Vitess(PlanetScale) documentation below for more information. |
| sqlalchemy_url      | False    | None    | Example mysql://[username]:[password]@localhost:3306/[db_name] |
| ssh_tunnel                   | False    | None    | SSH Tunnel Configuration, this is a json object |
| ssh_tunnel.enable   | True (if ssh_tunnel set) | False   | Enable an ssh tunnel (also known as bastion host), see the other ssh_tunnel.* properties for more details.
| ssh_tunnel.host | True (if ssh_tunnel set) | False   | Host of the bastion host, this is the host we'll connect to via ssh
| ssh_tunnel.username | True (if ssh_tunnel set) | False   |Username to connect to bastion host
| ssh_tunnel.port | True (if ssh_tunnel set) | 22 | Port to connect to bastion host
| ssh_tunnel.private_key | True (if ssh_tunnel set) | None | Private Key for authentication to the bastion host
| ssh_tunnel.private_key_password | False | None | Private Key Password, leave None if no password is set
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

### SSH Tunnels (Bastion Hosts)

This tap supports connecting to a Postgres database via an SSH tunnel (also known as a bastion host). This is useful if you need to connect to a database that is not publicly accessible. This is the same as using `ssh -L` and `ssh -R`, but this is done inside the tap itself.

## Usage

You can easily run `tap-mysql` by itself or in a pipeline using [Meltano](https://meltano.com/).


### Executing the Tap Directly

```bash
tap-mysql --version
tap-mysql --help
tap-mysql --config CONFIG --discover > ./catalog.json
```

### PlanetScale(Vitess) Support
To get planetscale to work you need to use SSL.

config example in meltano.yml
```yaml
      host: aws.connect.psdb.cloud
      user: 01234fdsoi99
      database: tap-mysql
      sql_options:
        ssl_ca: "/etc/ssl/certs/ca-certificates.crt"
        ssl_verify_cert: "true"
        ssl_verify_identity: "true"
```

Example select in meltano.yml (Which excludes tables that will fail)
```yaml
    select:
    - "*.*"
    - "!information_schema-PROFILING.*"
    - "!performance_schema-log_status.*"
```

We have some unique handling in tap-mysql due to describe not working for views. Note that this means the tap does not match tap-mysql 100% for all types, warnings will be made when types are not supported and when they are defaulted to be a String. Two example of this are enum, and set types.

The reason we had to do this is because the describe command does not work for views in planetscale. The core issue is shown by trying to run the sql command below

```sql
> describe information_schema.collations;
ERROR 1049 (42000): VT05003: unknown database 'information_schema' in vschema
```

#### PlanetScale Supported Tap
Note that PlanetScale has a singer tap that they support. It's located here https://github.com/planetscale/singer-tap/
It's written in Go, and it also supports Log Based replication.
This is a great alternative to this tap if you're using PlanetScale.

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
