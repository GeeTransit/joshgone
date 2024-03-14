# JoshGone

A Discord bot with some random commands.

## Setup

Clone the repo using [Git](https://git-scm.com/downloads) and enter it using the commands below:

```sh
git clone https://github.com/GeeTransit/joshgone
cd joshgone
```

Install [Python](https://www.python.org/downloads/) (minimum is 3.9) and create the virtual environment by running:

```sh
# On Windows
python -m venv .venv
# On Linux
python3 -m venv .venv
```

To enter the virtual environment, run the following. To leave the virtual environment, type `deactivate` and press enter.

```sh
# On Windows
call .venv\Scripts\activate.bat
# On Linux
source .venv/bin/activate
```

Install all dependencies by entering the virtual environment and running:

```sh
# On Windows
pip install -r requirements.txt
# On Linux
pip3 install -r requirements.txt
```

If installing the dependencies failed, this is likely because the `requirements.txt` file was generated on Windows. You can try manually `pip install`ing the dependencies listed in `hatch.toml` under `[envs.default]`.

## Config

JoshGone takes all configuration using environment variables. Here's a table with the environment variables needed.

| Name           | Purpose                                                      |
| -------------- | ------------------------------------------------------------ |
| JOSHGONE_TOKEN | Discord bot user's token. Should be around 59 characters long and look random. |
| JOSHGONE_DB    | SQLite database location. Set it to `joshgone.db`.           |
| JOSHGONE_REPL  | Optional. Can be `0` (default) or `1`. If it is `1`, there will be a REPL after the bot starts. |

You can get your Discord bot user's token by going to [your dashboard](https://discord.com/developers/applications), clicking on your application, clicking *Bot* in the left sidebar, and pressing the *Copy* button under *Token* in the *Build-A-Bot* section.

If you don't have an application, click *New Application* on the top right and choose a name (you can change it later).

If you don't have a bot user, press *Add Bot* in the *Build-a-Bot* section and click *Yes, do it!*

To set an environment variable, run:

```sh
# On Windows
set NAME=value
# On Linux
export NAME=value
```

## More Setup

Create or update the database to the newest format by entering the virtual environment and running:

```sh
yoyo apply
```

For playing music to work, you need to have [FFmpeg](http://ffmpeg.org/) on your PATH environment variable. Verify by running:

```sh
ffmpeg -version
```

## Usage

Enter the virtual environment and run:

```sh
# On Windows
python joshgone.py
# On Linux
python3 joshgone.py
```

## Online Sequencer

*Note: This is very experimental.*

For playing music from Online Sequencer to work, you need to install from `requirements-os.txt` instead of `requirements.txt`. For more info on how it gets the sequence notes, check out `online_sequencer_get_note_infos.py`.

Next, run the following command in the virtual environment. This will download the instrument settings and the audio file for each instrument into a directory named oscollection.

```sh
# On Windows
python online_sequencer_download.py oscollection
# On Linux
python3 online_sequencer_download.py oscollection
```

If you want to use a different directory name, replace oscollection with the different name in the command, and set the JOSHGONE_OS_DIRECTORY environment variable to the different name.

## Development

Install [Hatch](https://hatch.pypa.io/latest/install/) globally (I recommend using [pipx](https://pipx.pypa.io/stable/installation/)).

JoshGone uses Hatch mainly to manage virtual environments. The `requirements.txt` file is generated from the `default` environment by a [Hatch plugin](https://juftin.com/hatch-pip-compile/), and likewise with the `requirements-os.txt` from the `os` environment.

To enter a Hatch-managed virtual environment, run the following. To leave the virtual environment, type `exit` and press enter.

```sh
hatch --env default shell
```

The environment defaults to `default`, so you can omit `--env default` if you wish.

To run a command inside an environment, there is a faster way using the `run` subcommand:

```sh
hatch --env default run ...
```

To add a dependency, go to `hatch.toml` and add to the `dependencies` list. The next time you enter the environment, the corresponding requirements file will be updated.
