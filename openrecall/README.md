I forked it because the original author has not updated it for a while. I have fixed some bugs according to [origin issue#107](https://github.com/openrecall/openrecall/issues/107) & [origin issue#104](https://github.com/openrecall/openrecall/issues/104) and try to make it better. I hope it will be helpful to you.

## todo list
- [ ] make a simple executable file to install
- [ ] make a pyproject.toml for packaging
- [ ] add support for Python 3.13 and above
- [ ] make it more accurate
- [ ] run on GPU if needed
------
```
   ____                   ____                  ____   
  / __ \____  ___  ____  / __ \___  _________ _/ / /   
 / / / / __ \/ _ \/ __ \/ /_/ / _ \/ ___/ __ `/ / /    
/ /_/ / /_/ /  __/ / / / _, _/  __/ /__/ /_/ / / /     
\____/ .___/\___/_/ /_/_/ |_|\___/\___/\__,_/_/_/      
    /_/                                                                                                                         
```
**Enjoy this project?** Show your support by starring it! ⭐️ Thank you!

# Take Control of Your Digital Memory

OpenRecall is a fully open-source, privacy-first alternative to proprietary solutions like Microsoft's Windows Recall or Limitless' Rewind.ai. With OpenRecall, you can easily access your digital history, enhancing your memory and productivity without compromising your privacy.

## What does it do?

OpenRecall captures your digital history through regularly taken snapshots, which are essentially screenshots. The text and images within these screenshots are analyzed and made searchable, allowing you to quickly find specific information by typing relevant keywords into OpenRecall. You can also manually scroll back through your history to revisit past activities.

https://github.com/cute-omega/openrecall/assets/16676419/cfc579cb-165b-43e4-9325-9160da6487d2

## Why Choose OpenRecall?

OpenRecall offers several key advantages over closed-source alternatives:

- **Transparency**: OpenRecall is 100% open-source, allowing you to audit the source code for potential backdoors or privacy-invading features.
- **Cross-platform Support**: OpenRecall works on Windows, macOS, and Linux, giving you the freedom to use it on your preferred operating system.
- **Privacy-focused**: Your data is stored locally on your device, no internet connection or cloud is required. In addition, you have the option to encrypt the data on a removable disk for added security, read how in our [guide](docs/encryption.md) here. 
- **Hardware Compatibility**: OpenRecall is designed to work with a [wide range of hardware](docs/hardware.md), unlike proprietary solutions that may require specific certified devices.

<p align="center">
  <a href="https://twitter.com/elonmusk/status/1792690964672450971" target="_blank">
    <img src="images/black_mirror.png" alt="Elon Musk Tweet" width="400">
  </a>
</p>

## Features

- **Time Travel**: Revisit and explore your past digital activities seamlessly across Windows, macOS, or Linux.
- **Local-First AI**: OpenRecall harnesses the power of local AI processing to keep your data private and secure.
- **Semantic Search**: Advanced local OCR interprets your history, providing robust semantic search capabilities.
- **Full Control Over Storage**: Your data is stored locally, giving you complete control over its management and security.

<p align="center">
  <img src="images/lisa_rewind.webp" alt="Lisa Rewind" width="400">
</p>


## Comparison



| Feature            | OpenRecall             | Windows Recall                                     | Rewind.ai            |
|--------------------|------------------------|----------------------------------------------------|----------------------|
| Transparency       | Open-source            | Closed-source                                      | Closed-source        |
| Supported Hardware | All                    | Copilot+ certified Windows hardware                | M1/M2 Apple Silicon  |
| OS Support         | Windows, macOS, Linux  | Windows                                            | macOS                |
| Privacy            | On-device, self-hosted | Microsoft's privacy policy applies                 | Connected to ChatGPT |
| Cost               | Free                   | Part of Windows 11 (requires specialized hardware) | Monthly subscription |

## Quick links
- [FAQ](https://github.com/openrecall/openrecall/wiki/FAQ)

## Get Started

### Prerequisites
- Python 3.9-3.12
- MacOSX/Windows/Linux
- Git

To install:
```
python3 -m pip install --upgrade --no-cache-dir git+https://github.com/cute-omega/openrecall.git
```

To run:
```
python3 -m openrecall.app
```
Open your browser to:
[http://localhost:8083](http://localhost:8083) to access OpenRecall.

## Configuration

OpenRecall uses environment variables for configuration:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENRECALL_DATA_DIR` | `~/.myrecall_data` | Path where screenshots and database are stored. We recommend [creating an encrypted volume](docs/encryption.md) to store your data. |
| `OPENRECALL_PORT` | `8083` | Web server port |
| `OPENRECALL_PRIMARY_MONITOR_ONLY` | `false` | Only record the primary monitor (rather than individual screenshots for other monitors) |

Example:
```bash
OPENRECALL_DATA_DIR=/path/to/encrypted/volume python3 -m openrecall.app
```

## Uninstall instructions

To uninstall OpenRecall and remove all stored data:

1. Uninstall the package:
   ```
   python3 -m pip uninstall openrecall
   ```

2. Remove stored data:
   - On all platforms:
     ```shell
     rm -rf ~/.myrecall_data
     ```

Note: If you specified a custom storage path using the `OPENRECALL_DATA_DIR` environment variable, make sure to remove that directory too.

## Contribute

As an open-source project, we welcome contributions from the community. If you'd like to help improve OpenRecall, please submit a pull request or open an issue on our GitHub repository.

## License

OpenRecall is released under the [AGPLv3](https://opensource.org/licenses/AGPL-3.0), ensuring that it remains open and accessible to everyone.
