import nodemailer, { type Transporter } from "nodemailer";

export const EMAIL_VERIFICATION_TTL_SECONDS = 10 * 60;
export const EMAIL_VERIFICATION_RESEND_SECONDS = 60;
export const EMAIL_VERIFICATION_MAX_ATTEMPTS = 5;

export interface RegistrationVerificationEmailSender {
  sendRegistrationCode(email: string, code: string): Promise<void>;
}

export interface SmtpConfig {
  host: string;
  port: number;
  secure: boolean;
  user: string;
  password: string;
  from: string;
  maxConcurrency: number;
}

export class NodemailerRegistrationVerificationEmailSender
  implements RegistrationVerificationEmailSender
{
  private readonly transporter: Transporter;

  constructor(private readonly config: SmtpConfig) {
    this.transporter = nodemailer.createTransport({
      host: config.host,
      port: config.port,
      secure: config.secure,
      pool: true,
      maxConnections: config.maxConcurrency,
      requireTLS: !config.secure,
      auth: {
        user: config.user,
        pass: config.password,
      },
      connectionTimeout: 10_000,
      greetingTimeout: 10_000,
      socketTimeout: 15_000,
    });
  }

  async sendRegistrationCode(
    email: string,
    code: string,
  ): Promise<void> {
    const result = await this.transporter.sendMail({
      from: this.config.from,
      to: email,
      subject: "My English 注册验证码",
      text: [
        `你的 My English 注册验证码是：${code}`,
        "",
        "验证码将在 10 分钟后过期，且只能用于完成一次注册。",
        "如果这不是你的操作，请忽略这封邮件。",
      ].join("\n"),
    });
    if (result.accepted.length === 0 || result.rejected.length > 0) {
      throw new Error("SMTP did not accept the verification message.");
    }
  }
}
