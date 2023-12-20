class PortGenerator:
    def __init__(self, start_port):
        self.start_port = start_port
        self.current_port = start_port

    def get_port(self):
        self.current_port += 1
        return self.current_port
