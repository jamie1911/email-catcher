import React from "react";
import { Icon } from "@aws-amplify/ui-react";

import {
  MdEmail,
} from "react-icons/md";

export const baseConfig = {
  projectLink: null, // GitHub link in the navbar
  docsRepositoryBase: "", // base URL for the docs repository
  titleSuffix: "",
  search: false,
  header: true,
  headerText: "Email Catcher",
  footer: true,
  footerText: (
    <>
      <span>
        © Baldanza Solutions {new Date().getFullYear()}
      </span>
    </>
  ),

  logo: (
    <>
      <img
        src={process.env.PUBLIC_URL + "/logo.png"}
        alt="logo"
        width="30"
        height="22"
      />
    </>
  ),
};

/// Navigation sidebar
export const appNavs = [
  {
    eventKey: "email-accounts",
    icon: <Icon as={MdEmail} />,
    title: "Emails",
    to: "/email-accounts",
    children: [
      {
        eventKey: "email-accounts",
        title: "Accounts",
        to: "/email-accounts",
      },
    ],
  },
];
