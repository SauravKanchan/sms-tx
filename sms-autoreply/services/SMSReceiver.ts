import { Alert } from 'react-native';
import { debugLogger } from './DebugLogger';

export interface SMSMessage {
  address: string;
  body: string;
  date: string;
  type?: string;
}

export class SMSReceiver {
  private isListening = false;
  private onMessageReceived?: (message: SMSMessage) => void;

  async initialize(): Promise<boolean> {
    try {
      debugLogger.info('PERMISSION', 'Initializing SMS receiver (mock implementation)');
      console.log('SMS receiver initialized (mock implementation)');
      Alert.alert(
        'SMS Receiver',
        'This is a mock implementation. In a production app with proper SMS reading permissions, this would check and request SMS permissions.',
        [{ text: 'OK' }]
      );
      debugLogger.success('PERMISSION', 'SMS receiver initialized successfully');
      return true;
    } catch (error) {
      debugLogger.error('PERMISSION', 'Failed to initialize SMS receiver', error);
      console.error('Error initializing SMS permissions:', error);
      return false;
    }
  }

  startListening(onMessageReceived: (message: SMSMessage) => void): void {
    if (this.isListening) {
      debugLogger.warning('SMS_RECEIVE', 'SMS listener already running');
      console.log('SMS listener already running');
      return;
    }

    this.onMessageReceived = onMessageReceived;

    try {
      debugLogger.info('SMS_RECEIVE', 'Starting mock SMS listener...');
      console.log('Starting mock SMS listener...');
      this.isListening = true;

      // Simulate receiving an SMS after 5 seconds for testing
      setTimeout(() => {
        debugLogger.info('SMS_RECEIVE', 'Simulating received SMS...');
        console.log('Simulating received SMS...');
        if (this.onMessageReceived) {
          const mockMessage: SMSMessage = {
            address: '+1234567890',
            body: 'Hello, this is a test message for the auto-reply system!',
            date: new Date().toISOString(),
            type: 'received'
          };
          debugLogger.success('SMS_RECEIVE', 'Mock SMS received', {
            from: mockMessage.address,
            message: mockMessage.body
          });
          this.onMessageReceived(mockMessage);
        }
      }, 5000);

      debugLogger.success('SMS_RECEIVE', 'Mock SMS listener started successfully');
      console.log('Mock SMS listener started successfully');
      Alert.alert(
        'SMS Listener Started',
        'Mock SMS listener is running. A test message will be simulated in 5 seconds.',
        [{ text: 'OK' }]
      );
    } catch (error) {
      debugLogger.error('SMS_RECEIVE', 'Failed to start SMS listener', error);
      console.error('Failed to start SMS listener:', error);
    }
  }

  stopListening(): void {
    this.isListening = false;
    this.onMessageReceived = undefined;
    debugLogger.info('SMS_RECEIVE', 'SMS listener stopped');
    console.log('SMS listener stopped');
  }

  isCurrentlyListening(): boolean {
    return this.isListening;
  }
}

export const smsReceiver = new SMSReceiver();