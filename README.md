# JoshGone

A Discord bot with some random commands.

## Setup

Clone the repo using [Git](https://git-scm.com/downloads) and enter it using the commands below:

```sh
git clone https://github.com/GeeTransit/joshgone
cd joshgone
```

Install [Python](https://www.python.org/downloads/) (minimum is 3.9).

Install [Hatch](https://hatch.pypa.io/latest/install/) globally (I recommend using [pipx](https://pipx.pypa.io/stable/installation/)).

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

Create or update the database to the newest format by running:

```sh
hatch run yoyo apply
```

For playing music to work, you need to have [FFmpeg](http://ffmpeg.org/) on your PATH environment variable. Verify by running:

```sh
ffmpeg -version
```

## Usage

Run:

```sh
hatch run python joshgone.py
```

## Online Sequencer

*Note: This is very experimental.*

For playing music from Online Sequencer to work, use `hatch -e os ...` instead of `hatch ...` to use the OS environment (which has extra dependencies). For more info on how it gets the sequence notes, check out `online_sequencer_get_note_infos.py`.

Next, run the following command. This will download the instrument settings and the audio file for each instrument into a directory named oscollection.

```sh
hatch -e os run python online_sequencer_download.py oscollection
```

If you want to use a different directory name, replace oscollection with the different name in the command, and set the JOSHGONE_OS_DIRECTORY environment variable to the different name.

## Development

JoshGone uses Hatch mainly to manage virtual environments. The `requirements.txt` file is generated from the `default` environment by a [Hatch plugin](https://juftin.com/hatch-pip-compile/), and likewise with the `requirements-os.txt` from the `os` environment.

To add a dependency, go to `hatch.toml` and add to the `dependencies` list. The next time you enter the environment, the corresponding requirements file will be updated.
