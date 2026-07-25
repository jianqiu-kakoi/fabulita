declare module "node:crypto" {
  export function createHash(algorithm: string): {
    update(value: string): {
      digest(encoding: "hex"): string;
    };
  };
  export function randomUUID(): string;
}

declare module "@cloudbase/js-sdk" {
  interface CloudBaseApp {
    auth: {
      getUserInfo(): {
        uid?: string;
        openId?: string;
        customUserId?: string;
      };
    };
    database(): unknown;
  }

  const cloudbase: {
    init(options: Record<string, unknown>): CloudBaseApp;
  };

  export default cloudbase;
}

declare const process: {
  env: Record<string, string | undefined>;
};
