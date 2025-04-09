export interface User {
  name: string;
  email: string;
  roles: string[];
}

export interface SmartModeState {
  isEnabled: boolean;
  lastToggle: number;
}

export interface HistoryItem {
  type: 'text' | 'image';
  content: string;
  imageData?: string;
}

export interface CommandResult {
  text: string;
}

export interface MessageContent {
  type: string;
  content: string | CommandResult[];
  tool?: string;
  command?: string;
  format?: string;
}

export interface ServerMessage {
  role: string;
  content: string | MessageContent[];
}

export interface ServerResponse {
  output?: string;
  type?: string;
  messages?: ServerMessage[];
} 