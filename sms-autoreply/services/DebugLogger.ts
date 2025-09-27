export interface LogEntry {
  id: string;
  timestamp: Date;
  level: 'info' | 'warning' | 'error' | 'success';
  category: 'SMS_RECEIVE' | 'SMS_SEND' | 'BACKGROUND' | 'PERMISSION' | 'SYSTEM' | 'API' | 'PHONE_VALIDATION';
  message: string;
  data?: any;
}

export class DebugLogger {
  private logs: LogEntry[] = [];
  private listeners: ((logs: LogEntry[]) => void)[] = [];
  private maxLogs = 100;

  private generateId(): string {
    return Date.now().toString(36) + Math.random().toString(36).substr(2);
  }

  addLog(
    level: LogEntry['level'],
    category: LogEntry['category'],
    message: string,
    data?: any
  ): void {
    const entry: LogEntry = {
      id: this.generateId(),
      timestamp: new Date(),
      level,
      category,
      message,
      data
    };

    this.logs.unshift(entry);

    // Keep only the most recent logs
    if (this.logs.length > this.maxLogs) {
      this.logs = this.logs.slice(0, this.maxLogs);
    }

    // Also log to console for debugging
    const consoleMessage = `[${category}] ${message}`;
    switch (level) {
      case 'success':
        console.log(`✅ ${consoleMessage}`, data);
        break;
      default:
        console.log(consoleMessage, data);
    }

    // Notify all listeners
    this.listeners.forEach(listener => listener([...this.logs]));
  }

  info(category: LogEntry['category'], message: string, data?: any): void {
    this.addLog('info', category, message, data);
  }

  warning(category: LogEntry['category'], message: string, data?: any): void {
    this.addLog('warning', category, message, data);
  }

  error(category: LogEntry['category'], message: string, data?: any): void {
    this.addLog('error', category, message, data);
  }

  success(category: LogEntry['category'], message: string, data?: any): void {
    this.addLog('success', category, message, data);
  }

  // Subscribe to log updates
  subscribe(listener: (logs: LogEntry[]) => void): () => void {
    this.listeners.push(listener);

    // Send current logs immediately
    listener([...this.logs]);

    // Return unsubscribe function
    return () => {
      const index = this.listeners.indexOf(listener);
      if (index > -1) {
        this.listeners.splice(index, 1);
      }
    };
  }

  // Get all logs
  getLogs(): LogEntry[] {
    return [...this.logs];
  }

  // Clear all logs
  clearLogs(): void {
    this.logs = [];
    this.listeners.forEach(listener => listener([]));
    this.info('SYSTEM', 'Debug logs cleared');
  }

  // Export logs as JSON string
  exportLogs(): string {
    return JSON.stringify(this.logs, null, 2);
  }

  // Get logs by category
  getLogsByCategory(category: LogEntry['category']): LogEntry[] {
    return this.logs.filter(log => log.category === category);
  }

  // Get logs by level
  getLogsByLevel(level: LogEntry['level']): LogEntry[] {
    return this.logs.filter(log => log.level === level);
  }
}

export const debugLogger = new DebugLogger();