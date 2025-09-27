import * as SMS from 'expo-sms';
import { Platform, Linking } from 'react-native';
import { debugLogger } from './DebugLogger';

export interface SMSSendResult {
  success: boolean;
  message?: string;
  error?: string;
}

export class NativeSMSSender {
  async checkSMSAvailability(): Promise<boolean> {
    try {
      debugLogger.info('PERMISSION', 'Checking SMS availability...');
      const isAvailable = await SMS.isAvailableAsync();
      debugLogger.success('PERMISSION', `SMS availability: ${isAvailable}`);
      return isAvailable;
    } catch (error) {
      debugLogger.error('PERMISSION', 'Error checking SMS availability', error);
      console.error('Error checking SMS availability:', error);
      return false;
    }
  }

  async sendSMS(phoneNumber: string, message: string): Promise<SMSSendResult> {
    try {
      debugLogger.info('SMS_SEND', `Attempting to send SMS to ${phoneNumber}`, { message });

      if (!phoneNumber || !message) {
        debugLogger.error('SMS_SEND', 'Phone number and message are required');
        return {
          success: false,
          error: 'Phone number and message are required'
        };
      }

      const isAvailable = await this.checkSMSAvailability();
      if (!isAvailable) {
        debugLogger.error('SMS_SEND', 'SMS is not available on this device');
        return {
          success: false,
          error: 'SMS is not available on this device'
        };
      }

      console.log(`Attempting to send SMS to ${phoneNumber}: ${message}`);

      if (Platform.OS === 'android') {
        return await this.sendSMSAndroid(phoneNumber, message);
      } else {
        return await this.sendSMSIOS(phoneNumber, message);
      }
    } catch (error) {
      debugLogger.error('SMS_SEND', 'Error sending SMS', error);
      console.error('Error sending SMS:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred'
      };
    }
  }

  private async sendSMSAndroid(phoneNumber: string, message: string): Promise<SMSSendResult> {
    try {
      debugLogger.info('SMS_SEND', 'Using Android SMS Intent method');
      const smsUrl = `sms:${phoneNumber}?body=${encodeURIComponent(message)}`;

      const canOpen = await Linking.canOpenURL(smsUrl);
      if (!canOpen) {
        debugLogger.error('SMS_SEND', 'Cannot open SMS app on this device');
        return {
          success: false,
          error: 'Cannot open SMS app on this device'
        };
      }

      await Linking.openURL(smsUrl);
      debugLogger.success('SMS_SEND', 'SMS app opened successfully', { to: phoneNumber, method: 'Android Intent' });

      return {
        success: true,
        message: 'SMS app opened with pre-filled message'
      };
    } catch (error) {
      debugLogger.error('SMS_SEND', 'Android SMS error', error);
      return {
        success: false,
        error: `Android SMS error: ${error}`
      };
    }
  }

  private async sendSMSIOS(phoneNumber: string, message: string): Promise<SMSSendResult> {
    try {
      debugLogger.info('SMS_SEND', 'Using iOS SMS API method');
      const result = await SMS.sendSMSAsync([phoneNumber], message);

      if (result.result === 'sent') {
        debugLogger.success('SMS_SEND', 'SMS sent successfully via iOS API', { to: phoneNumber, result: result.result });
        return {
          success: true,
          message: 'SMS sent successfully'
        };
      } else if (result.result === 'cancelled') {
        debugLogger.warning('SMS_SEND', 'SMS was cancelled by user', { to: phoneNumber, result: result.result });
        return {
          success: false,
          error: 'SMS was cancelled by user'
        };
      } else {
        debugLogger.error('SMS_SEND', 'SMS sending failed or unknown result', { to: phoneNumber, result: result.result });
        return {
          success: false,
          error: 'SMS sending failed or unknown result'
        };
      }
    } catch (error) {
      debugLogger.error('SMS_SEND', 'iOS SMS error', error);
      return {
        success: false,
        error: `iOS SMS error: ${error}`
      };
    }
  }

  async sendAutoReply(phoneNumber: string, originalMessage: string): Promise<SMSSendResult> {
    const replyMessage = this.generateAutoReply(originalMessage);
    debugLogger.info('SMS_SEND', 'Generating auto-reply', {
      to: phoneNumber,
      originalMessage,
      autoReply: replyMessage
    });
    return this.sendSMS(phoneNumber, replyMessage);
  }

  private generateAutoReply(originalMessage: string): string {
    const message = originalMessage.toLowerCase().trim();

    if (message.includes('hello') || message.includes('hi') || message.includes('hey')) {
      return 'Hello! Thank you for your message. This is an automated response.';
    }

    if (message.includes('help') || message.includes('support')) {
      return 'I received your request for help. This is an automated system. Someone will get back to you soon.';
    }

    if (message.includes('thank') || message.includes('thanks')) {
      return 'You\'re welcome! This is an automated response.';
    }

    if (message.includes('stop') || message.includes('unsubscribe')) {
      return 'You have been unsubscribed from automated messages.';
    }

    if (message.includes('info') || message.includes('information')) {
      return 'This is an automated SMS reply system. For more information, please contact support.';
    }

    return 'Thank you for your message. This is an automated response. Your message has been received and will be processed.';
  }
}

export const nativeSMSSender = new NativeSMSSender();