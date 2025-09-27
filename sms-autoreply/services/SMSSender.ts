import { nativeSMSSender } from './NativeSMSSender';

export interface SMSSendResult {
  success: boolean;
  message?: string;
  error?: string;
}

export class SMSSender {
  async sendSMS(phoneNumber: string, message: string): Promise<SMSSendResult> {
    return nativeSMSSender.sendSMS(phoneNumber, message);
  }

  async sendAutoReply(phoneNumber: string, originalMessage: string): Promise<SMSSendResult> {
    return nativeSMSSender.sendAutoReply(phoneNumber, originalMessage);
  }
}

export const smsSender = new SMSSender();