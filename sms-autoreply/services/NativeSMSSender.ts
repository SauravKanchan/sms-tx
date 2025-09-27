// NativeSMSSender.ts
import { Platform, PermissionsAndroid } from 'react-native';
import { debugLogger } from './DebugLogger';

export interface SMSSendResult {
  success: boolean;
  message?: string;
  error?: string;
}

// --- Config: API endpoint ---
// Android emulator: use 10.0.2.2 instead of localhost
const BASE_URL =
  Platform.OS === 'android' ? 'http://10.0.2.2:3001' : 'http://localhost:3001';
const TX_API = `${BASE_URL}/api/transaction`;

// --- Import react-native-mobile-sms ---
let mobileSms: any = null;
try {
  const lib = require('react-native-mobile-sms');
  mobileSms = lib?.MobileSms ?? lib?.default ?? lib;
  debugLogger.info('SMS_SEND', 'react-native-mobile-sms loaded', {
    hasSendDirectSms: !!mobileSms?.sendDirectSms,
    keys: mobileSms ? Object.keys(mobileSms) : 'null',
  });
} catch (e) {
  debugLogger.warning('SMS_SEND', 'react-native-mobile-sms not found', e);
}

export class NativeSMSSender {
  async checkSMSPermissions(): Promise<boolean> {
    try {
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
        const ok = granted === PermissionsAndroid.RESULTS.GRANTED;
        debugLogger.success('PERMISSION', `SMS send permission: ${ok}`);
        return ok;
      }
      debugLogger.success('PERMISSION', 'iOS: composer-only (no silent send)');
      return true;
    } catch (error) {
      debugLogger.error('PERMISSION', 'Error checking SMS permissions', error);
      return false;
    }
  }

  async sendSMS(phoneNumber: string, message: string): Promise<SMSSendResult> {
    try {
      const hasPermission = await this.checkSMSPermissions();
      if (!hasPermission) {
        const error = 'SMS sending permission not granted';
        return { success: false, error };
      }
      return await this.sendDirectSMS(phoneNumber, message);
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred',
      };
    }
  }

  private async sendDirectSMS(phoneNumber: string, message: string): Promise<SMSSendResult> {
    if (Platform.OS === 'android' && typeof mobileSms?.sendDirectSms === 'function') {
      try {
        debugLogger.info('SMS_SEND', 'Using MobileSms.sendDirectSms');
        const maybePromise = mobileSms.sendDirectSms.length >= 3
          ? new Promise<void>((resolve, reject) => {
              mobileSms.sendDirectSms(
                phoneNumber,
                message,
                (success: boolean, msg: string) => {
                  if (success) resolve();
                  else reject(new Error(msg || 'sendDirectSms failed'));
                }
              );
            })
          : mobileSms.sendDirectSms(phoneNumber, message);

        await maybePromise;
        debugLogger.success('SMS_SEND', 'Direct SMS sent', { to: phoneNumber });
        return { success: true, message: 'SMS sent directly (sendDirectSms)' };
      } catch (error) {
        debugLogger.error('SMS_SEND', 'Direct SMS error', error);
        return { success: false, error: (error as Error).message };
      }
    }

    const error = 'Direct SMS not available on this platform/build';
    debugLogger.error('SMS_SEND', error);
    return { success: false, error };
  }

  // --- Auto-reply: use API response ---
  async sendAutoReply(phoneNumber: string, _originalMessage: string): Promise<SMSSendResult> {
    try {
      const apiResponseText = await this.callTransactionAPI();
      const smsBody = this.prepareSmsBody(apiResponseText);
      debugLogger.info('SMS_SEND', 'Auto-reply using API response', {
        to: phoneNumber,
        preview: smsBody.slice(0, 120),
      });
      return await this.sendSMS(phoneNumber, smsBody);
    } catch (error) {
      const fallback = `API error: ${(error as Error)?.message ?? 'unknown'}`;
      return await this.sendSMS(phoneNumber, fallback);
    }
  }

  private async callTransactionAPI(): Promise<string> {
    const payload = {
      sender: 'saurav@example.com',
      receiver: 'shreya@example.com',
      amount: '1.2',
    };

    debugLogger.info('API', 'POST /api/transaction', { url: TX_API, payload });

    const res = await fetch(TX_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const text = await res.text();
    debugLogger.info('API', 'Response', { status: res.status, bodyPreview: text.slice(0, 200) });
    return text || `Empty response (status ${res.status})`;
  }

  private prepareSmsBody(raw: string): string {
    const MAX = 480; // multi-part SMS limit
    if (raw.length <= MAX) return raw;
    const compact = raw.replace(/\s+/g, ' ').trim();
    return compact.length <= MAX ? compact : compact.slice(0, MAX - 10) + '...';
  }
}

export const nativeSMSSender = new NativeSMSSender();
