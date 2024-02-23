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
| is_vitess           | False    | None    | By default we'll check if the database is a Vitess instance. If you'd rather not automatically check, set this to `False`. See Vitess/ PlanetScale documentation below for more information. |
| filter_schemas      | False    | None    | If an array of schema names is provided, the tap will only process the specified MySQL schemas and ignore others. If left blank, the tap automatically determines ALL available MySQL schemas. |
| sqlalchemy_options             | False    | None    | This needs to be passed in as a JSON Object. sqlalchemy_url options (also called the query), to connect to PlanetScale you must turn on SSL. See the PlanetScale section below for details. Note: if `sqlalchemy_url` is set this will be ignored. |
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

This tap supports connecting to a MySQL database via an SSH tunnel (also known as a bastion host). This is useful if you need to connect to a database that is not publicly accessible. This is the same as using `ssh -L` and `ssh -R`, but this is done inside the tap itself.

## What is an SSH Tunnel?

An SSH tunnel is a method to securely forward network traffic. It uses the SSH protocol to encapsulate other protocols like HTTP, MySQL, Postgres, etc. This is particularly useful in scenarios where you need to access a service that is behind a firewall or in a network that you can't reach directly. In the context of this tap, you can use an SSH tunnel to access a MySQL database that's not accessible to the wider internet.

Here's a basic illustration of how an SSH tunnel works:
```
+-------------+             +-------------+             +-------------+
|    Local    | SSH tunnel  |   Bastion   |   Direct    |    MySQL    |
|   Machine   | <=========> |   Server    | <=========> |     DB      |
+-------------+ (encrypted) +-------------+ (unsecured) +-------------+
```

1. Local Machine: This is wherever this tap is running from, where you initiate the SSH tunnel. It's also referred to as the SSH client.
1. Bastion Server: This is a secure server that you have SSH access to, and that can connect to the remote server. All traffic in the SSH tunnel between your local machine and the bastion server is encrypted.
1. Remote Server: This is the server you want to connect to, in this case a MySQL server. The connection between the bastion server and the remote server is a normal, potentially unsecured connection. However, because the bastion server is trusted, and because all traffic between your local machine and the bastion server is encrypted, you can safely transmit data to and from the remote server.

### Obtaining Keys

Setup
1. Ensure your bastion server is online.
1. Ensure you bastion server can access your MySQL database.
1. Have some method of accessing your bastion server. This could either be through password-based SSH authentication or through a hardwired connection to the server.
1. Install `ssh-keygen` on your client machine if it is not already installed.

Creating Keys
1. Run the command `ssh-keygen`.
    1. Enter the directory where you would like to save your key. If you're in doubt, the default directory is probably fine.
        - If you get a message similar to the one below asking if you wish to overwrite a previous key, enter `n`, then rerun `ssh-keygen` and manually specify the output_keyfile using the `-f` flag.
            ```
            /root/.ssh/id_rsa already exists.
            Overwrite (y/n)?
            ```
    1. If you wish, enter a passphrase to provide additional protection to your private key. SSH-based authentication is generally considered secure even without a passphrase, but a passphrase can provide an additional layer of security.
    1. You should now be presented with a message similar to the following, as well as a key fingerprint and ascii randomart image.
        ```
        Your identification has been saved in /root/.ssh/id_rsa
        Your public key has been saved in /root/.ssh/id_rsa.pub
        ```
1. Navigate to the indicated directory and find the two keys that were just generated. The file named `id_rsa` is your private key. Keep it safe. The file named `id_rsa.pub` is your public key, and needs to be transferred to your bastion server for your private key to be used.

Copying Keys
1. Now that you have a pair of keys, the public key needs to be transferred to your bastion server.
1. If you already have password-based SSH authentication configured, you can use the command `ssh-copy-id [user]@[host]` to copy your public key to the bastion server. Then you can move on to [using your keys](#using-your-keys)
1. If not, you'll need some other way to access your bastion server. Once you've accessed it, copy the `id_rsa.pub` file onto the bastion server in the `~/.ssh/authorized_keys` file. You could do this using a tool such as `rsync` or with a cloud-based service.
    - Keep in mind: it's okay if your public key is exposed to the internet through a file-share or something similar. It is useless without your private key.

### Using Your Keys

To connect through SSH, you will need to determine the following pieces of information. If you're missing something, go back to [the section on Obtaining Keys](#obtaining-keys) to gather all the relevant information.
 - The connection details for your MySQL database, the same as any other tap-mysql run. This includes host, port, user, password and database.
   - Alternatively, provide an sqlalchemy url. Keep in mind that many other configuration options are ignored when an sqlalchemy url is set, and ideally you should be able to accomplish everything through other configuration options. Consider making a [tap-mysql issue](https://github.com/MeltanoLabs/tap-mysql/issues/new) if you find a reasonable use-case that is unsupported by current configuration options.
   - Note that when your connection details are used, it will be from the perspective of the bastion server. This could change the meaning of local IP address or keywords such as "localhost".
 - The hostname or ip address of the bastion server, provided in the `ssh.host` configuration option.
 - The port for use with the bastion server, provided in the `ssh.port` configuration option.
 - The username for authentication with the bastion server, provided in the `ssh.username` configuration option. This will require you to have setup an SSH login with the bastion server.
 - The private key you use for authentication with the bastion server, provided in the `ssh.private_key` configuration option. If your private key is protected by a password (alternatively called a "private key passphrase"), provide it in the `ssh.private_key_password` configuration option. If your private key doesn't have a password, you can safely leave this field blank.

After everything has been configured, be sure to indicate your use of an ssh tunnel to the tap by configuring the `ssh.enable` configuration option to be `True`. Then, you should be able to connect to your privately accessible MySQL database through the bastion server.

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
