# Android Automation Suite - DroidForge

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg)]()

**DroidForge** is a comprehensive, production-ready Android automation framework that provides programmatic control over Android devices through ADB. Built with developers, testers, and automation enthusiasts in mind, it offers a rich set of features from basic touch gestures to advanced computer vision capabilities.

##  Features

### Core Capabilities
- **Device Management** - Automatic device discovery, connection management, and wireless ADB setup
- **Gesture Control** - Tap, swipe, pinch, long press, and keyboard input with coordinate scaling
- **Screen Capture** - Screenshots with region cropping and screen recording with customizable parameters
- **Computer Vision** - OCR text detection and template-based image matching for element location
- **Macro System** - Record, save, and playback complex automation sequences
- **Performance Monitoring** - Real-time CPU, memory, and battery usage tracking for any application

### Advanced Features
- **Web Control Panel** - Local web interface with API token authentication for remote control
- **SQLite Persistence** - Store macros, device information, and settings locally
- **Multi-Device Support** - Handle multiple Android devices simultaneously
- **Interactive CLI** - Rich command-line interface for quick operations
- **Extensible Architecture** - Modular design makes it easy to add new features

## Prerequisites

- **Python 3.8+** - Core runtime
- **ADB (Android Debug Bridge)** - Required for device communication
- **Android Device** - With USB debugging enabled
- **Optional Dependencies**:
  - Tesseract OCR - For text recognition features
  - OpenCV - For advanced computer vision capabilities
  - Flask - For web interface functionality

## Quick Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/droidforge.git
cd droidforge

# Install core dependencies
pip install -r requirements.txt

# Optional: Install OCR support
pip install pytesseract pillow
sudo apt-get install tesseract-ocr  # Ubuntu/Debian
# or
brew install tesseract  # macOS
```

## Basic Usage

### Command Line Interface

```bash
# List connected devices
python droidforge.py --devices

# Take a screenshot
python droidforge.py --screenshot

# Tap at coordinates (1080x1920 resolution)
python droidforge.py --tap 540 960

# Type text
python droidforge.py --text "Hello World"

# Record macro
python droidforge.py --macro-record login_flow

# Play macro
python droidforge.py --macro-play login_flow

# Monitor app performance
python droidforge.py --monitor-perf com.example.app 30

# Start web interface
python droidforge.py --web 8080
```

### Interactive Mode

```bash
python droidforge.py --interactive
```

Interactive commands:
```
devices                      - List all connected devices
select <device_id>          - Select active device
screenshot                   - Capture screen
tap 540 960                  - Tap at coordinates
swipe 540 1600 540 800      - Swipe gesture
macro record login           - Start macro recording
macro play login             - Play recorded macro
ocr                          - Detect text on screen
find template.png            - Find and tap image
monitor com.example.app 30   - Performance monitoring
wireless                     - Setup wireless ADB
web 8080                     - Start web interface
```

### Python API

```python
from droidforge import AndroidAutomation

# Initialize the automation suite
automation = AndroidAutomation()

# List available devices
devices = automation.list_devices()

# Select a device
automation.device_manager.select_device(devices[0]["id"])

# Perform gestures
automation.gesture.tap(540, 960)
automation.gesture.type_text("Hello from Python")

# Take screenshot
automation.screen_capture.take_screenshot()

# Record and play macro
automation.macro_recorder.start_recording("my_macro")
automation.gesture.tap(100, 200)
automation.macro_recorder.stop_recording()
automation.macro_recorder.play_macro("my_macro", automation.gesture)

# OCR text detection
text = automation.vision.detect_text()
print(f"Detected: {text}")

# Performance monitoring
metrics = automation.performance_monitor.monitor_app("com.example.app", duration=10)
```

## Web Interface

Start the web control panel with:

```bash
python droidforge.py --web 5000
```

The interface provides:
- Real-time device monitoring
- Visual screenshot capture
- Macro recording and playback
- Gesture control from browser
- API token authentication

Access at: `http://127.0.0.1:5000`

## Architecture

```
droidforge/
├── core/
│   ├── adb_client.py      # ADB communication layer
│   ├── device_manager.py   # Device discovery and management
│   ├── gesture.py          # Touch and keyboard control
│   └── screen_capture.py   # Screenshot and recording
├── vision/
│   ├── ocr.py              # Text detection
│   └── template_match.py   # Image matching
├── macros/
│   ├── recorder.py         # Macro recording
│   └── player.py           # Macro playback
├── web/
│   ├── server.py           # Flask web interface
│   └── static/             # Web assets
├── storage/
│   └── database.py         # SQLite persistence
└── monitor/
    └── performance.py      # App performance metrics
```

## Security

- Web interface runs on localhost only by default
- API token authentication for all web endpoints
- No external data transmission
- All data stored locally in `~/.android_automation/`

## Performance

- **Screenshot capture**: < 1 second
- **Template matching**: 100-300ms
- **OCR processing**: 500-2000ms depending on image size
- **ADB command overhead**: 50-100ms average

## Troubleshooting

### Common Issues

**Device not detected:**
```bash
adb kill-server
adb start-server
adb devices
```

**Wireless connection fails:**
```bash
# Ensure USB debugging is enabled
# Connect via USB first, then:
adb tcpip 5555
adb connect <device_ip>:5555
```

**OCR not working:**
```bash
# Install Tesseract
sudo apt-get install tesseract-ocr tesseract-ocr-eng
# Verify installation
tesseract --version
```

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
# Clone with development dependencies
git clone https://github.com/yourusername/droidforge.git
cd droidforge
pip install -e ".[dev]"

# Run tests
pytest tests/

# Check code style
flake8 droidforge/
black droidforge/
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Google for ADB and Android platform tools
- OpenCV community for computer vision capabilities
- Tesseract OCR team for text recognition
- All contributors and users of this project

## Support & Community

- **GitHub Issues**: [Report bugs or request features](https://github.com/yourusername/droidforge/issues)
- **Discussions**: [Join the community](https://github.com/yourusername/droidforge/discussions)
- **Documentation**: [Full documentation](https://droidforge.readthedocs.io/)

## Roadmap

- [ ] iOS device support via WebDriverAgent
- [ ] Visual test recorder
- [ ] Cloud device farm integration
- [ ] CI/CD pipeline integration
- [ ] GUI application
- [ ] Plugin system for extensions
- [ ] Device screen mirroring
- [ ] Automated test generation

---

**Built with ❤️ for Android automation** | [Report Bug](https://github.com/yourusername/droidforge/issues) | [Request Feature](https://github.com/yourusername/droidforge/issues)

