import React from "react";
import { Routes, Route, Link } from "react-router-dom";
import "@aws-amplify/ui-react/styles.css";
import "./App.css";
import { ThemeProvider } from "@aws-amplify/ui-react";
import theme from "./theme";

import { Amplify } from 'aws-amplify';
import { fetchAuthSession } from 'aws-amplify/auth'
import awsExports from './aws-exports';

import Layout from "./components/Layout";
import EmailAccounts from "./pages/email-accounts";
import EmailMessages from "./pages/email-messages";
import EmailMessage from "./pages/email-message";


Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: awsExports.userPoolId,
      userPoolClientId: awsExports.userPoolWebClientId
    }
  },
  API: {
    REST: {
      disposible: {
        endpoint: awsExports.apiGatewayurl,
      }
    }
  }
}, {
  API: {
    REST: {
      headers: async () => {
        const authToken = (await fetchAuthSession()).tokens?.idToken?.toString();
        if (!authToken) {
          return {
            Authorization: "",
          };
        }
        return {
          Authorization: authToken,
        };
      }
    }
  }
});


export default function App() {
  return (
    <ThemeProvider theme={theme}>
      {/* Routes nest inside one another. Nested route paths build upon
            parent route paths, and nested route elements render inside
            parent route elements. See the note about <Outlet> below. */}
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<EmailAccounts />} />
          <Route path="email-accounts" element={<EmailAccounts />} />
          <Route path="email-accounts/:addressId" element={<EmailMessages />} />
          <Route path="email-accounts/:addressId/:messageId" element={<EmailMessage />} />
          <Route path="*" element={<NoMatch />} />
        </Route>
      </Routes>
    </ThemeProvider>
  );
}

function NoMatch() {
  return (
    <div>
      <h2>Nothing to see here!</h2>
      <p>
        <Link to="/email-accounts">Go to the home page</Link>
      </p>
    </div>
  );
}
