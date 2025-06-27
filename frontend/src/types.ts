export interface User {
  name: string;
  email: string;
  roles: string[];
}


export interface HistoryItem {
  type: 'text' | 'image' | 'progress';
  content: string;
  imageData?: string;
  toolName?: string;
  status?: 'running' | 'completed' | 'error';
  output?: unknown;
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

export interface StreamUpdate {
  type: 'status' | 'tool_start' | 'tool_result' | 'conversation' | 'error' | 'assistant_response';
  message?: string;
  tool_name?: string;
  command?: string;
  success?: boolean;
  output?: unknown;
  error?: string;
  content?: unknown;
  messages?: ServerMessage[];
  response?: string;
} 