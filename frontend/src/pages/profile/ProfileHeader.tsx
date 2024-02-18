import React from "react";
import { Flex, Text } from "@aws-amplify/ui-react";

interface ProfileHeaderProps {
  name?: string;
  email?: string;
  imageSrc?: string;
}

const ProfileHeader = (props: ProfileHeaderProps) => {
  console.log(props);
  return (
    <>
      <Flex
        direction={{ base: "column", large: "row" }}
        alignItems="flex-start"
      >
        <div className="profile-header-image">
          <img alt="avatar" src={process.env.PUBLIC_URL + "/profile.png"}></img>
        </div>
        <div className="profile-header-text">
          <Text variation="primary" fontWeight={600} fontSize="18px">
            Clark Mathews
          </Text>
          <Text variation="tertiary">clarkmathews@gmail.com</Text>
        </div>
      </Flex>
    </>
  );
};

export default ProfileHeader;
