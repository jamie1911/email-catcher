import React from "react";
import { Menu, MenuItem, MenuButton, Link } from "@aws-amplify/ui-react";
import { useNavigate } from "react-router-dom";
import { AiFillGithub } from "react-icons/ai";
import { baseConfig } from "../../config";
import { signOut } from 'aws-amplify/auth';

const HeaderNav = () => {
  const navigate = useNavigate();

  return (
    <>
      {baseConfig.projectLink ? (
        <div className="github-link">
          <Link
            href={baseConfig.projectLink}
            isExternal={true}
            ariaLabel="github"
          >
            <AiFillGithub />
          </Link>
        </div>
      ) : (
        <></>
      )}

      <Menu
        menuAlign="end"
        trigger={
          <MenuButton variation="menu">
            <div className="header-avatar">
              <img alt="avatar" src={process.env.PUBLIC_URL + "/profile.png"}></img>
            </div>
          </MenuButton>
        }
      >
        <MenuItem onClick={() => navigate("/profile")}>Profile</MenuItem>
        <MenuItem onClick={() => signOut()}>Logout</MenuItem>
      </Menu>
    </>
  );
};
export default HeaderNav;
