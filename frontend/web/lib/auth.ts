import NextAuth from 'next-auth';
import GoogleProvider from 'next-auth/providers/google';

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID || '',
      clientSecret: process.env.GOOGLE_CLIENT_SECRET || '',
      authorization: { params: { scope: 'openid email profile' } },
    }),
    // WeChat OAuth (placeholder — 等待微信开放平台审核)
    // WeChatProvider({ clientId: ..., clientSecret: ... }),
  ],
  pages: {
    signIn: '/login',
  },
  callbacks: {
    async jwt({ token, account }) {
      if (account) token.accessToken = account.access_token;
      return token;
    },
    async session({ session, token }) {
      return { ...session, accessToken: token.accessToken };
    },
  },
  session: { strategy: 'jwt' },
});
