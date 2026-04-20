/**
 * Cliente GraphQL centralizado.
 * Usa graphql-request con la URL del backend configurada vía proxy Vite en dev
 * y variable de entorno VITE_API_URL en producción.
 */
import { GraphQLClient } from 'graphql-request'

const endpoint = (import.meta.env.VITE_API_URL ?? '') + '/graphql'

export const gqlClient = new GraphQLClient(endpoint, {
  headers: {},
})
