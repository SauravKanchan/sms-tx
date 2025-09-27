// NativeSMSSender.ts
import { Platform, PermissionsAndroid } from 'react-native';
import { debugLogger } from './DebugLogger';

export interface SMSSendResult {
  success: boolean;
  message?: string;
  error?: string;
}

interface TransactionResponse {
  amount: string;
  receiver_address: string;
  sender_address: string;
  success: boolean;
  tx_hash: string;
}

// --- Config: API endpoint (prod) ---
const BASE_URL = 'https://28fox.com';
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
      debugLogger.info('SMS_SEND', 'Sending SMS', { phoneNumber, message });
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
        debugLogger.info('SMS_SEND', 'Using MobileSms.sendDirectSms', { phoneNumber, message });
        await mobileSms.sendDirectSms(phoneNumber, message);
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
      const transactionResponse = await this.callTransactionAPI();
      const smsBody = this.createTransactionMessage(transactionResponse);
      const finalMessage = this.prepareSmsBody(smsBody);

      debugLogger.info('SMS_SEND', 'Auto-reply using transaction response', {
        to: phoneNumber,
        txHash: transactionResponse.tx_hash,
        preview: finalMessage.slice(0, 120),
      });

      return await this.sendSMS(phoneNumber, finalMessage);
    } catch (error) {
      const fallback = `Transaction failed: ${(error as Error)?.message ?? 'unknown'}`;
      debugLogger.error('API', 'Auto-reply failed', { error: error });
      return await this.sendSMS(phoneNumber, fallback);
    }
  }

  private async callTransactionAPI(): Promise<TransactionResponse> {
    const payload = {
      sender: 'saurav@example.com',
      receiver: 'shreya@example.com',
      amount: '1.2',
    };

    debugLogger.info('API', 'POST /api/transaction', { url: TX_API, payload });

    try {
      // Create timeout controller
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout

      const res = await fetch(TX_API, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          'User-Agent': 'SMS-AutoReply/1.0'
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }

      const text = await res.text();
      debugLogger.info('API', 'Response', { status: res.status, bodyPreview: text.slice(0, 200) });

      if (!text) {
        throw new Error(`Empty response (status ${res.status})`);
      }

      try {
        const jsonResponse: TransactionResponse = JSON.parse(text);
        if (!jsonResponse.success || !jsonResponse.tx_hash) {
          throw new Error('Transaction failed or missing tx_hash');
        }
        return jsonResponse;
      } catch (parseError) {
        debugLogger.error('API', 'Failed to parse JSON response', { text, parseError });
        throw new Error('Invalid JSON response from transaction API');
      }
    } catch (error) {
      debugLogger.error('API', 'Network request failed', {
        error: error instanceof Error ? error.message : 'Unknown error',
        url: TX_API,
        errorType: error instanceof TypeError ? 'Network/TypeError' : 'Other'
      });

      // Re-throw with more context
      if (error instanceof TypeError && error.message.includes('Network request failed')) {
        throw new Error('Network request failed - check internet connection and network security config');
      }
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new Error('Request timed out after 10 seconds');
      }
      throw error;
    }
  }

  private formatTransactionLink(txHash: string): string {
    // Ensure tx_hash has 0x prefix for the URL
    const formattedHash = txHash.startsWith('0x') ? txHash : `0x${txHash}`;
    return `https://sepolia.arbiscan.io/tx/${formattedHash}`;
  }

  private createTransactionMessage(response: TransactionResponse): string {
    const transactionLink = this.formatTransactionLink(response.tx_hash);
    return `Transaction successful! View transaction: ${transactionLink}`;
  }

  private prepareSmsBody(raw: string): string {
    const MAX = 480; // safe multi-part size
    if (raw.length <= MAX) return raw;
    const compact = raw.replace(/\s+/g, ' ').trim();
    return compact.length <= MAX ? compact : compact.slice(0, MAX - 10) + '...';
  }
}

export const nativeSMSSender = new NativeSMSSender();
