// Types pour l'utilisateur
export type UserRole = 'admin' | 'user' | 'guest';

export interface User {
  name: string;
  email: string;
  roles: UserRole[];
}


// Types pour les éléments d'historique
export type HistoryItemType = 'text' | 'user-message' | 'image' | 'progress';
export type ProgressStatus = 'running' | 'completed' | 'error';

export interface BaseHistoryItem {
  type: HistoryItemType;
  content: string;
}

export interface TextHistoryItem extends BaseHistoryItem {
  type: 'text';
}

export interface UserMessageHistoryItem extends BaseHistoryItem {
  type: 'user-message';
}

export interface ImageHistoryItem extends BaseHistoryItem {
  type: 'image';
  imageData: string;
}

export interface ProgressHistoryItem extends BaseHistoryItem {
  type: 'progress';
  toolName?: string;
  status?: ProgressStatus;
  output?: unknown;
}

export type HistoryItem = TextHistoryItem | UserMessageHistoryItem | ImageHistoryItem | ProgressHistoryItem;

// Types pour les messages du serveur (utilisés dans useStreaming)
export interface ServerMessage {
  role: string;
  content: string | Array<{
    type: string;
    content: string | Array<{ text: string }>;
    tool?: string;
    command?: string;
    format?: string;
  }>;
}

// Types pour les mises à jour de streaming
export type StreamUpdateType = 'status' | 'tool_start' | 'tool_result' | 'conversation' | 'error' | 'assistant_response';

export interface BaseStreamUpdate {
  type: StreamUpdateType;
}

export interface StatusStreamUpdate extends BaseStreamUpdate {
  type: 'status';
  message?: string;
}

export interface ToolStartStreamUpdate extends BaseStreamUpdate {
  type: 'tool_start';
  tool_name: string;
  command: string;
}

export interface ToolResultStreamUpdate extends BaseStreamUpdate {
  type: 'tool_result';
  success: boolean;
  output?: unknown;
  error?: string;
}

export interface ConversationStreamUpdate extends BaseStreamUpdate {
  type: 'conversation';
  messages: ServerMessage[];
}

export interface ErrorStreamUpdate extends BaseStreamUpdate {
  type: 'error';
  message: string;
}

export interface AssistantResponseStreamUpdate extends BaseStreamUpdate {
  type: 'assistant_response';
  response?: string;
}

export type StreamUpdate = 
  | StatusStreamUpdate 
  | ToolStartStreamUpdate 
  | ToolResultStreamUpdate 
  | ConversationStreamUpdate 
  | ErrorStreamUpdate 
  | AssistantResponseStreamUpdate;

// Types utilitaires
export type ApiResponse<T> = {
  data?: T;
  error?: string;
  success: boolean;
};

export type LoadingState = 'idle' | 'loading' | 'success' | 'error'; 