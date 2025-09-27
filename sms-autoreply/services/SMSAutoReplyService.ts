import { smsReceiver, SMSMessage } from './SMSReceiver';
import { smsSender } from './SMSSender';
import { debugLogger } from './DebugLogger';

export interface AutoReplyStats {
  messagesReceived: number;
  messagesReplied: number;
  errors: number;
  lastMessage?: SMSMessage;
  lastReply?: string;
  isActive: boolean;
}

export class SMSAutoReplyService {
  private stats: AutoReplyStats = {
    messagesReceived: 0,
    messagesReplied: 0,
    errors: 0,
    isActive: false
  };

  private onStatsUpdate?: (stats: AutoReplyStats) => void;

  async start(onStatsUpdate?: (stats: AutoReplyStats) => void): Promise<boolean> {
    if (this.stats.isActive) {
      debugLogger.warning('SYSTEM', 'SMS Auto-Reply service is already running');
      console.log('SMS Auto-Reply service is already running');
      return true;
    }

    this.onStatsUpdate = onStatsUpdate;

    try {
      debugLogger.info('SYSTEM', 'Starting SMS Auto-Reply service...');
      const initialized = await smsReceiver.initialize();
      if (!initialized) {
        debugLogger.error('SYSTEM', 'Failed to initialize SMS receiver');
        console.error('Failed to initialize SMS receiver');
        return false;
      }

      smsReceiver.startListening(this.handleIncomingSMS.bind(this));

      this.stats.isActive = true;
      this.updateStats();

      debugLogger.success('SYSTEM', 'SMS Auto-Reply service started successfully');
      console.log('SMS Auto-Reply service started successfully');
      return true;
    } catch (error) {
      debugLogger.error('SYSTEM', 'Failed to start SMS Auto-Reply service', error);
      console.error('Failed to start SMS Auto-Reply service:', error);
      return false;
    }
  }

  stop(): void {
    if (!this.stats.isActive) {
      debugLogger.warning('SYSTEM', 'SMS Auto-Reply service is not running');
      console.log('SMS Auto-Reply service is not running');
      return;
    }

    debugLogger.info('SYSTEM', 'Stopping SMS Auto-Reply service...');
    smsReceiver.stopListening();
    this.stats.isActive = false;
    this.updateStats();

    debugLogger.success('SYSTEM', 'SMS Auto-Reply service stopped');
    console.log('SMS Auto-Reply service stopped');
  }

  private async handleIncomingSMS(message: SMSMessage): Promise<void> {
    debugLogger.info('SYSTEM', 'Processing incoming SMS for auto-reply', {
      from: message.address,
      message: message.body,
      timestamp: message.date
    });
    console.log('Processing incoming SMS:', message);

    this.stats.messagesReceived++;
    this.stats.lastMessage = message;
    this.updateStats();

    try {
      const replyResult = await smsSender.sendAutoReply(message.address, message.body);

      if (replyResult.success) {
        this.stats.messagesReplied++;
        this.stats.lastReply = 'Auto-reply sent successfully';
        debugLogger.success('SYSTEM', `Auto-reply sent to ${message.address}`, {
          replyMessage: replyResult.message
        });
        console.log(`Auto-reply sent to ${message.address}`);
      } else {
        this.stats.errors++;
        this.stats.lastReply = `Failed to send: ${replyResult.error}`;
        debugLogger.error('SYSTEM', `Failed to send auto-reply to ${message.address}`, {
          error: replyResult.error
        });
        console.error(`Failed to send auto-reply to ${message.address}:`, replyResult.error);
      }
    } catch (error) {
      this.stats.errors++;
      this.stats.lastReply = `Error: ${error}`;
      debugLogger.error('SYSTEM', 'Error processing auto-reply', error);
      console.error('Error processing auto-reply:', error);
    }

    this.updateStats();
  }

  private updateStats(): void {
    if (this.onStatsUpdate) {
      this.onStatsUpdate({ ...this.stats });
    }
  }

  getStats(): AutoReplyStats {
    return { ...this.stats };
  }

  resetStats(): void {
    this.stats = {
      messagesReceived: 0,
      messagesReplied: 0,
      errors: 0,
      isActive: this.stats.isActive
    };
    this.updateStats();
  }

  isRunning(): boolean {
    return this.stats.isActive;
  }
}

export const smsAutoReplyService = new SMSAutoReplyService();