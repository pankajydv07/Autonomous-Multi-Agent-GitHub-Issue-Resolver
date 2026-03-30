import { ApolloServer } from '@apollo/server';
import { expressMiddleware } from '@apollo/server/express4';
import { ApolloServerPluginDrainHttpServer } from '@apollo/server/plugin/drainHttpServer';
import { makeExecutableSchema } from '@graphql-tools/schema';
import cors from 'cors';
import express from 'express';
import http from 'http';
import { WebSocketServer } from 'ws';
import { useServer } from 'graphql-ws/lib/use/ws';

import { typeDefs } from './schema/typeDefs.js';
import { resolvers } from './resolvers/index.js';

const PORT = Number(process.env.PORT || 4000);

async function startServer() {
  const schema = makeExecutableSchema({ typeDefs, resolvers });

  const app = express();
  const httpServer = http.createServer(app);

  const wsServer = new WebSocketServer({
    server: httpServer,
    path: '/graphql',
  });

  const serverCleanup = useServer({ schema }, wsServer);

  const apolloServer = new ApolloServer({
    schema,
    plugins: [
      ApolloServerPluginDrainHttpServer({ httpServer }),
      {
        async serverWillStart() {
          return {
            async drainServer() {
              await serverCleanup.dispose();
            },
          };
        },
      },
    ],
  });

  await apolloServer.start();

  app.use('/graphql', cors<cors.CorsRequest>(), express.json(), expressMiddleware(apolloServer));

  await new Promise<void>((resolve) => {
    httpServer.listen(PORT, () => resolve());
  });

  console.log(`🚀 Gateway ready at http://localhost:${PORT}/graphql`);
  console.log(`🔌 WebSocket ready at ws://localhost:${PORT}/graphql`);
}

startServer().catch(console.error);
