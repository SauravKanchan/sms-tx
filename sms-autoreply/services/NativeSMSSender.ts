// NativeSMSSender.ts
import { Platform, PermissionsAndroid } from 'react-native';
import { debugLogger } from './DebugLogger';
import { PhoneUtils } from './PhoneUtils';

export interface SMSSendResult {
  success: boolean;
  message?: string;
  error?: string;
}

interface AIAPIResponse {
  data: string; // Arbiscan URL or address
  from?: string; // Optional: sender phone number (for transactions)
  to?: string; // Optional: recipient phone number (for transactions)
  amount?: string; // Optional: transaction amount (for transactions)
}

// --- Config: API endpoint (prod) ---
const BASE_URL = 'https://28fox.com';
const AI_API = `${BASE_URL}/api/ai`;

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

  // --- Auto-reply: use AI API response ---
  async sendAutoReply(phoneNumber: string, originalMessage: string): Promise<SMSSendResult> {
    try {
      // Validate input
      if (!phoneNumber || !originalMessage) {
        throw new Error('Phone number and message are required');
      }

      // Format phone number and validate
      const formattedPhone = PhoneUtils.formatPhoneNumber(phoneNumber);
      if (!PhoneUtils.isValidPhoneNumber(phoneNumber)) {
        debugLogger.warning('SMS_SEND', 'Invalid phone number format', {
          original: phoneNumber,
          formatted: formattedPhone
        });
      }

      const aiMessage = PhoneUtils.createAIMessage(formattedPhone, originalMessage);

      debugLogger.info('SMS_SEND', 'Processing message through AI API', {
        from: formattedPhone,
        originalMessage,
        aiMessage
      });

      const aiResponse = await this.callAIAPI(aiMessage);

      // Check if this is a transaction response
      if (this.isTransactionResponse(aiResponse)) {
        debugLogger.info('SMS_SEND', 'Transaction detected - sending dual SMS', {
          from: aiResponse.from,
          to: aiResponse.to,
          amount: aiResponse.amount,
          transactionLink: aiResponse.data
        });

        // Send notification to recipient
        const recipientMessage = this.createRecipientNotification(aiResponse.amount!);
        const recipientResult = await this.sendSMS(aiResponse.to!, recipientMessage);

        if (!recipientResult.success) {
          debugLogger.error('SMS_SEND', 'Failed to send recipient notification', {
            to: aiResponse.to,
            error: recipientResult.error
          });
        } else {
          debugLogger.success('SMS_SEND', 'Recipient notification sent', {
            to: aiResponse.to,
            message: recipientMessage
          });
        }

        // Send transaction link to sender (original requester)
        const senderMessage = this.prepareSmsBody(aiResponse.data);
        const senderResult = await this.sendSMS(phoneNumber, senderMessage);

        debugLogger.info('SMS_SEND', 'Transaction SMS responses completed', {
          senderSuccess: senderResult.success,
          recipientSuccess: recipientResult.success,
          senderMessage: senderMessage.slice(0, 120)
        });

        return senderResult; // Return sender result as primary response
      } else {
        // Non-transaction response - send only to original sender
        const finalMessage = this.prepareSmsBody(aiResponse.data);

        debugLogger.info('SMS_SEND', 'Non-transaction response - sending to sender only', {
          to: formattedPhone,
          response: aiResponse.data,
          preview: finalMessage.slice(0, 120),
        });

        return await this.sendSMS(phoneNumber, finalMessage);
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown error';

      // Create user-friendly fallback message
      let fallback = 'Sorry, unable to process your request at the moment.';
      if (errorMsg.includes('Network request failed')) {
        fallback = 'Service temporarily unavailable. Please try again later.';
      } else if (errorMsg.includes('timeout')) {
        fallback = 'Request timed out. Please try again.';
      } else if (errorMsg.includes('parse') || errorMsg.includes('JSON')) {
        fallback = 'Invalid response from service. Please try again.';
      }

      debugLogger.error('API', 'Auto-reply failed', {
        error: errorMsg,
        originalMessage,
        phoneNumber
      });

      return await this.sendSMS(phoneNumber, fallback);
    }
  }

  private async callAIAPI(message: string): Promise<AIAPIResponse> {
    const payload = {
      message: message,
    };

    debugLogger.info('API', 'POST /api/ai', { url: AI_API, payload });

    try {
      // Create timeout controller
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000); // 15 second timeout

      const res = await fetch(AI_API, {
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
      debugLogger.info('API', 'AI API Response', { status: res.status, bodyPreview: text.slice(0, 200) });

      if (!text) {
        throw new Error(`Empty response (status ${res.status})`);
      }

      try {
        const jsonResponse: AIAPIResponse = JSON.parse(text);
        if (!jsonResponse.data) {
          throw new Error('AI API response missing data field');
        }
        return jsonResponse;
      } catch (parseError) {
        debugLogger.error('API', 'Failed to parse JSON response', { text, parseError });
        throw new Error('Invalid JSON response from AI API');
      }
    } catch (error) {
      debugLogger.error('API', 'Network request failed', {
        error: error instanceof Error ? error.message : 'Unknown error',
        url: AI_API,
        errorType: error instanceof TypeError ? 'Network/TypeError' : 'Other'
      });

      // Re-throw with more context
      if (error instanceof TypeError && error.message.includes('Network request failed')) {
        throw new Error('Network request failed - check internet connection and network security config');
      }
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new Error('Request timed out after 15 seconds');
      }
      throw error;
    }
  }


  private prepareSmsBody(raw: string): string {
    const MAX = 480; // safe multi-part size
    if (raw.length <= MAX) return raw;
    const compact = raw.replace(/\s+/g, ' ').trim();
    return compact.length <= MAX ? compact : compact.slice(0, MAX - 10) + '...';
  }

  private isTransactionResponse(response: AIAPIResponse): boolean {
    return !!(response.from && response.to && response.amount);
  }

  private createRecipientNotification(amount: string): string {
    return `You have received ${amount} PyUSD`;
  }
}

export const nativeSMSSender = new NativeSMSSender();
