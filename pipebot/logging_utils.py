class Logger:
    def __init__(self, app_config, debug=False):
        self.app_config = app_config
        self.debug_enabled = debug
    
    def info(self, message: str):
        print(f"{self.app_config.colors.blue}[INFO] {message}{self.app_config.colors.reset}")
    
    def error(self, message: str):
        print(f"{self.app_config.colors.red}[ERROR] {message}{self.app_config.colors.reset}")
    
    def debug(self, message: str):
        if self.debug_enabled:
            print(f"{self.app_config.colors.blue}[DEBUG] {message}{self.app_config.colors.reset}")
    
    def success(self, message: str):
        print(f"{self.app_config.colors.green}[SUCCESS] {message}{self.app_config.colors.reset}")

    def warning(self, message: str):
        print(f"{self.app_config.colors.red}[WARNING] {message}{self.app_config.colors.reset}") 