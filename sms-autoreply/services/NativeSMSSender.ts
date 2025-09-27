// NativeSMSSender.ts
import { Platform, PermissionsAndroid } from 'react-native';
import { debugLogger } from './DebugLogger';
import * as SMS from 'expo-sms';

export interface SMSSendResult {
  success: boolean;
  message?: string;
  error?: string;
}

// --- Robust dynamic import for react-native-mobile-sms ---
let mobileSms: any = null;
try {
  const lib = require('react-native-mobile-sms');
  // Try common export shapes: named `MobileSms`, default export, or root.
  mobileSms = lib?.MobileSms ?? lib?.default ?? lib;

  debugLogger.info('SMS_SEND', 'react-native-mobile-sms loaded', {
    type: typeof mobileSms,
    keys: mobileSms ? Object.keys(mobileSms) : 'null',
    hasSendDirectSms: !!mobileSms?.sendDirectSms,
    hasSend: !!mobileSms?.send,
  });
} catch (error) {
  debugLogger.warning(
    'SMS_SEND',
    'react-native-mobile-sms not available, will use Expo SMS fallback',
    error
  );
}

export class NativeSMSSender {
  async checkSMSPermissions(): Promise<boolean> {
    try {
      debugLogger.info('PERMISSION', 'Checking SMS sending permissions...');

      if (Platform.OS === 'android') {
        const granted = await PermissionsAndroid.request(
          PermissionsAndroid.PERMISSIONS.SEND_SMS,
          {
            title: 'SMS Permission',
            message: 'This app needs SMS permission to send automatic replies',
            buttonNeutral: 'Ask Me Later',
            buttonNegative: 'Cancel',
            buttonPositive: 'OK',
          }
        );

        const hasPermission = granted === PermissionsAndroid.RESULTS.GRANTED;
        debugLogger.success('PERMISSION', `SMS send permission: ${hasPermission}`);
        return hasPermission;
      }

      // iOS cannot send silently; Expo path will open Messages composer.
      debugLogger.success('PERMISSION', 'SMS sending available on iOS (composer only)');
      return true;
    } catch (error) {
      debugLogger.error('PERMISSION', 'Error checking SMS permissions', error);
      return false;
    }
  }

  async sendSMS(phoneNumber: string, message: string): Promise<SMSSendResult> {
    try {
      debugLogger.info('SMS_SEND', `Attempting to send SMS to ${phoneNumber}`, { message });

      if (!phoneNumber || !message) {
        const error = 'Phone number and message are required';
        debugLogger.error('SMS_SEND', error);
        return { success: false, error };
      }

      const hasPermission = await this.checkSMSPermissions();
      if (!hasPermission) {
        const error = 'SMS sending permission not granted';
        debugLogger.error('SMS_SEND', error);
        return { success: false, error };
      }

      return await this.sendDirectSMS(phoneNumber, message);
    } catch (error) {
      debugLogger.error('SMS_SEND', 'Error sending SMS', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred',
      };
    }
  }

  private async sendDirectSMS(phoneNumber: string, message: string): Promise<SMSSendResult> {
    return new Promise(async (resolve) => {
      try {
        const info = {
          hasLib: !!mobileSms,
          hasSendDirectSms: !!mobileSms?.sendDirectSms,
          hasSend: !!mobileSms?.send,
          platform: Platform.OS,
        };
        debugLogger.info('SMS_SEND', 'Checking direct SMS availability', info);

        // Direct/background SMS is Android-only and requires the native module.
        if (Platform.OS === 'android' && mobileSms) {
          if (typeof mobileSms.sendDirectSms === 'function') {
            debugLogger.info('SMS_SEND', 'Using MobileSms.sendDirectSms');
            await mobileSms.sendDirectSms(
              phoneNumber,
              message
            );
            return;
          }

          if (typeof mobileSms.send === 'function') {
            debugLogger.info('SMS_SEND', 'Using MobileSms.send');
            mobileSms.send(
              phoneNumber,
              message,
              (success: boolean, msg: string) => {
                if (success) {
                  debugLogger.success('SMS_SEND', 'Direct SMS sent via send', {
                    to: phoneNumber,
                    method: 'send',
                  });
                  resolve({ success: true, message: 'SMS sent directly (send)' });
                } else {
                  debugLogger.error('SMS_SEND', 'send failed, falling back', { error: msg });
                  this.sendViaExpoSMS(phoneNumber, message, resolve);
                }
              }
            );
            return;
          }
        }

        debugLogger.warning('SMS_SEND', 'Direct SMS not available, using Expo SMS fallback');
        this.sendViaExpoSMS(phoneNumber, message, resolve);
      } catch (error) {
        debugLogger.error('SMS_SEND', 'Error with direct SMS, falling back to Expo SMS', error);
        this.sendViaExpoSMS(phoneNumber, message, resolve);
      }
    });
  }

  private async sendViaExpoSMS(
    phoneNumber: string,
    message: string,
    resolve: (result: SMSSendResult) => void
  ): Promise<void> {
    try {
      debugLogger.info('SMS_SEND', 'Using Expo SMS (will open messaging app)');

      const isAvailable = await SMS.isAvailableAsync();
      if (!isAvailable) {
        const error = 'SMS not available on this device';
        debugLogger.error('SMS_SEND', error);
        resolve({ success: false, error });
        return;
      }

      const result = await SMS.sendSMSAsync([phoneNumber], message);

      if (result.result === 'sent') {
        debugLogger.success('SMS_SEND', 'SMS sent via Expo (user-assisted)', {
          to: phoneNumber,
          method: 'expo-sms',
        });
        resolve({ success: true, message: 'SMS sent via messaging app (user-assisted)' });
      } else if (result.result === 'cancelled') {
        const error = 'SMS was cancelled by user';
        debugLogger.warning('SMS_SEND', error);
        resolve({ success: false, error });
      } else {
        const error = `SMS sending failed or unknown result: ${result.result}`;
        debugLogger.error('SMS_SEND', error);
        resolve({ success: false, error });
      }
    } catch (error) {
      debugLogger.error('SMS_SEND', 'Expo SMS error', error);
      resolve({
        success: false,
        error: `Expo SMS error: ${error instanceof Error ? error.message : String(error)}`,
      });
    }
  }

  async sendAutoReply(phoneNumber: string, originalMessage: string): Promise<SMSSendResult> {
    const replyMessage = this.generateAutoReply(originalMessage);
    debugLogger.info('SMS_SEND', 'Generating auto-reply', {
      to: phoneNumber,
      originalMessage,
      autoReply: replyMessage,
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
      return "You're welcome! This is an automated response.";
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
